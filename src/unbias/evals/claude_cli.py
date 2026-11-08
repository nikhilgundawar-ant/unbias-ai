"""Claude via headless Claude Code (`claude -p`), mode `cli_headless` (decision D16).

Limits, stated honestly:
- The CLI adds runtime context we cannot observe, so the provider request is NOT captured.
  Records carry `payload_capture: unavailable`; these runs are never strict-mode/G5 evidence.
- Text input is a single user message. Multi-turn histories are rendered as a labelled
  transcript (`history_rendering: transcript`), which is dev-only and never confirmatory.
- `--max-budget-usd` is a stopping control, not a billing guarantee. The run budget is enforced
  here by reserving the per-call cap before each call.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from typing import Any

from unbias.evals.runner import BudgetExhausted, ModelUnavailable, Reply

RunCmd = Callable[[list[str], str, float], "subprocess.CompletedProcess[str]"]

SAFE_FLAGS = (
    "--safe-mode",
    "--tools",
    "",
    "--no-session-persistence",
    "--max-turns",
    "1",
    "--output-format",
    "json",
)


def render_messages(messages: Sequence[dict[str, str]]) -> tuple[str, str]:
    """Return (prompt_text, history_rendering). Identical for every arm."""
    if len(messages) == 1 and messages[0]["role"] == "user":
        return messages[0]["content"], "single_turn"
    *history, last = messages
    lines = ["Earlier conversation (transcript):"]
    for m in history:
        lines.append(f"[{'User' if m['role'] == 'user' else 'Assistant'}]: {m['content']}")
    lines += ["", f"[User, new message]: {last['content']}"]
    return "\n".join(lines), "transcript"


def _default_run(cmd: list[str], cwd: str, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


class ClaudeCliClient:
    name = "claude_cli"
    is_mock = False

    def __init__(
        self,
        *,
        run_budget_usd: float = 2.0,
        per_call_cap_usd: float = 0.05,
        timeout_s: float = 120.0,
        max_retries: int = 1,
        executable: str = "claude",
        run_cmd: RunCmd = _default_run,
    ) -> None:
        if not 0 < per_call_cap_usd <= run_budget_usd:
            raise ValueError("need 0 < per_call_cap_usd <= run_budget_usd")
        self.run_budget_usd = run_budget_usd
        self.per_call_cap_usd = per_call_cap_usd
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.executable = executable
        self._run = run_cmd
        self.spent_usd = 0.0
        self.calls = 0
        self._cwd = tempfile.mkdtemp(prefix="unbias-cli-")  # outside any project config
        self.info: dict[str, Any] = {
            "mode": "cli_headless",
            "payload_capture": "unavailable",
            "safe_flags": list(SAFE_FLAGS),
            "run_budget_usd": run_budget_usd,
            "per_call_cap_usd": per_call_cap_usd,
            "timeout_s": timeout_s,
            "max_retries": max_retries,
            "cli_version": self._version(),
        }

    def _version(self) -> str:
        try:
            out = self._run([self.executable, "--version"], self._cwd, 30)
            return out.stdout.strip() or f"unknown (exit {out.returncode})"
        except Exception as e:  # recorded, not fatal
            return f"unknown ({type(e).__name__})"

    @staticmethod
    def _valid_cost(raw: Any) -> float | None:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        cost = float(raw)
        return cost if math.isfinite(cost) and cost >= 0 else None

    def _reserve(self) -> None:
        if self.spent_usd + self.per_call_cap_usd > self.run_budget_usd + 1e-12:
            raise BudgetExhausted(
                f"spent ${self.spent_usd:.4f}; next reservation ${self.per_call_cap_usd} "
                f"exceeds budget ${self.run_budget_usd}"
            )

    def complete(self, payload: dict[str, Any]) -> Reply:
        prompt, rendering = render_messages(payload["messages"])
        settings = payload["settings"]
        args = [
            self.executable,
            "-p",
            prompt,
            *SAFE_FLAGS,
            "--system-prompt",
            payload.get("system", ""),
            "--model",
            settings["model"],
            "--max-budget-usd",
            str(self.per_call_cap_usd),
        ]
        meta: dict[str, Any] = {
            "history_rendering": rendering,
            "rendered_prompt": prompt,
            "payload_capture": "unavailable",
            # Prompt and system text are already in the record; keep flags only here.
            "cli_args": [a for a in args if a not in (prompt, payload.get("system", ""))],
            "attempts": [],
        }
        last_error = "no attempt"
        for _attempt in range(self.max_retries + 1):
            try:
                self._reserve()
            except BudgetExhausted as e:
                partial = Reply(None, False, {}, error=f"budget exhausted: {e}", meta=meta)
                raise BudgetExhausted(str(e), partial if meta["attempts"] else None) from None
            self.calls += 1
            try:
                out = self._run(args, self._cwd, self.timeout_s)
            except subprocess.TimeoutExpired:
                self.spent_usd += self.per_call_cap_usd  # unknown cost: charge the reservation
                last_error = f"timeout after {self.timeout_s}s"
                meta["attempts"].append(
                    {
                        "error": last_error,
                        "cost_unknown": True,
                        "charged_usd": self.per_call_cap_usd,
                    }
                )
                continue
            try:
                data = json.loads(out.stdout)
                if not isinstance(data, dict):
                    raise ValueError("top-level JSON is not an object")
            except ValueError:  # JSONDecodeError is a ValueError
                self.spent_usd += self.per_call_cap_usd
                last_error = f"malformed output (exit {out.returncode}): {out.stderr[:300]}"
                meta["attempts"].append(
                    {
                        "error": last_error,
                        "cost_unknown": True,
                        "charged_usd": self.per_call_cap_usd,
                    }
                )
                continue
            # CX 13:41: unknown/invalid cost is charged the full reservation, never zero.
            attempt: dict[str, Any] = {"exit": out.returncode, "is_error": data.get("is_error")}
            cost = self._valid_cost(data.get("total_cost_usd"))
            if cost is None:
                attempt.update(cost_unknown=True, charged_usd=self.per_call_cap_usd)
                self.spent_usd += self.per_call_cap_usd
            else:
                attempt["cost_usd"] = cost
                if cost > self.per_call_cap_usd:
                    attempt["cost_exceeded_cap"] = True
                self.spent_usd += cost
            meta["attempts"].append(attempt)
            failed = out.returncode != 0 or data.get("is_error") or data.get("subtype") != "success"
            # CX 15:09: only an actual error envelope is inspected; answer text is data.
            if failed:
                status = data.get("api_error_status")
                text = str(data.get("result") or "") + out.stderr
                if status in (401, 403, 404) or re.search(
                    r"model.{0,40}(not found|not available|invalid|unsupported)|not_found_error",
                    text,
                    re.I,
                ):
                    msg = f"status={status}: {text[:200]}"
                    partial = Reply(None, False, {}, error=f"model unavailable: {msg}", meta=meta)
                    raise ModelUnavailable(msg, partial)
            if out.returncode != 0 or data.get("is_error") or data.get("subtype") != "success":
                last_error = (
                    f"cli error: exit {out.returncode} {data.get('subtype')} "
                    f"{data.get('api_error_status')}"
                )
                continue
            if not isinstance(data.get("result"), str):
                last_error = "success response without a text result"
                continue
            usage = data.get("usage") or {}
            model_usage = data.get("modelUsage") or {}
            effective = {
                "models": sorted(model_usage),
                "thinking_tokens": (usage.get("output_tokens_details") or {}).get(
                    "thinking_tokens"
                ),
                "stop_reason": data.get("stop_reason"),
                "service_tier": usage.get("service_tier"),
            }
            meta.update(
                cost_usd=cost, cost_unknown=cost is None, duration_ms=data.get("duration_ms")
            )
            return Reply(
                text=data.get("result"),
                is_mock=False,
                effective_settings=effective,
                usage={
                    k: int(usage.get(k) or 0)
                    for k in (
                        "input_tokens",
                        "output_tokens",
                        "cache_creation_input_tokens",
                        "cache_read_input_tokens",
                    )
                },
                meta=meta,
            )
        return Reply(None, False, {}, error=last_error, meta=meta)
