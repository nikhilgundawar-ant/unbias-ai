"""Efficacy-v2 arm runner: real headless Claude Code, with the product delivered by Claude Code
itself (CC analysis + CX EFFICACY_V2 §2). Never a hand-reconstructed hook note.

Each call runs in a FRESH temporary project whose `.claude/settings.json` registers only that
arm's hook. `--setting-sources project` keeps the user's own settings (output style, plugins,
effort) out of every arm. `--safe-mode` is NOT used, because it disables hooks.

Every call records evidence of what actually ran:
- the stream-json `init` event (model, tools, output style, plugins) -> contamination check;
- hook lifecycle events (`--include-hook-events`) -> delivery check against what
  `unbias.hook.run` produces for the same input.
A mismatch is a recorded protocol deviation, never silently accepted.

Budget/cost rules match ClaudeCliClient: the per-call cap is reserved before every attempt, and
unknown cost is charged the full reservation.
"""

from __future__ import annotations

import json
import math
import os
import shlex
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from unbias.evals.claude_cli import render_messages
from unbias.evals.runner import BudgetExhausted, Reply

RunCmd = Callable[[list[str], str, float], "subprocess.CompletedProcess[str]"]
NOOP_HOOK = "cat > /dev/null"  # identical hook machinery, adds nothing


@dataclass(frozen=True)
class ArmProfile:
    """One arm. `hook_command` None = no hook registered at all; NOOP_HOOK = placebo machinery.
    `append_system` uses --append-system-prompt, so Claude Code's DEFAULT system prompt stays
    in place, as for real users (past runs replaced it with --system-prompt)."""

    name: str
    hook_command: str | None
    append_system: str | None = None
    ledger_setup: tuple[tuple[str, ...], ...] = ()  # `unbias ledger ...` argv lists, run first
    notes: str = ""


@dataclass
class CallEvidence:
    init: dict[str, Any] | None = None
    hook_events: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    deviations: list[str] = field(default_factory=list)


def parse_stream(stdout: str) -> CallEvidence:
    """Tolerant stream-json parser: keeps init, every hook-related event, and the result."""
    ev = CallEvidence()
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            ev.deviations.append("non-JSON line in stream output")
            continue
        if not isinstance(obj, dict):
            continue
        kind = f"{obj.get('type', '')}/{obj.get('subtype', '')}"
        if kind == "system/init":
            ev.init = obj
        elif "hook" in kind.lower():
            ev.hook_events.append(obj)
        elif obj.get("type") == "result":
            ev.result = obj
    return ev


def _strings(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings(v)]
    return []


def delivered_context(ev: CallEvidence) -> str | None:
    """The additionalContext our hook returned, as recorded in the hook events, if any."""
    for e in ev.hook_events:
        for s in _strings(e):
            try:
                d = json.loads(s)
            except ValueError:
                d = None
            if isinstance(d, dict):
                ctx = (d.get("hookSpecificOutput") or {}).get("additionalContext")
                if isinstance(ctx, str):
                    return ctx
    return None


# Default-runtime builtins observed in the 2026-11-10 delivery smoke (CX 06:28 ACK). FROZEN:
# exact (name, path, source) triples for this CLI version only. Anything else is a deviation.
BUILTIN_PLUGIN_ALLOWLIST: dict[str, frozenset[tuple[str, str, str]]] = {
    "2.1.321": frozenset(
        (n, "builtin", f"{n}@builtin")
        for n in (
            "cc-plugin-agents-md",
            "cc-plugin-telemetry",
            "cc-plugin-privacy",
            "cc-plugin-plugin-authoring",
        )
    )
}
# init fields that legitimately differ per call; every other field must match across arms.
INCIDENTAL_INIT_FIELDS = frozenset(
    {"session_id", "uuid", "cwd", "original_cwd", "memory_paths", "messaging_socket_path"}
)


def _plugin_triple(p: Any) -> tuple[str, str, str] | None:
    if not isinstance(p, dict):
        return None
    vals = (p.get("name"), p.get("path"), p.get("source"))
    return vals if all(isinstance(v, str) and v for v in vals) else None  # type: ignore[return-value]


def check_init(init: dict[str, Any] | None, model: str) -> list[str]:
    """Contamination check on what Claude Code says it loaded."""
    if init is None:
        return ["no init event: configuration unverified"]
    out = []
    if init.get("tools"):
        out.append(f"tools loaded: {init.get('tools')}")
    style = init.get("output_style")
    if style not in (None, "default"):
        out.append(f"non-default output style: {style}")
    allowed = BUILTIN_PLUGIN_ALLOWLIST.get(str(init.get("claude_code_version")), frozenset())
    for p in init.get("plugins") or []:
        t = _plugin_triple(p)
        if t is None:
            out.append(f"plugin with missing metadata: {p!r}")
        elif t not in allowed:
            out.append(f"plugin not in frozen allowlist: {t}")
    if init.get("mcp_servers"):
        out.append(f"MCP servers loaded: {init.get('mcp_servers')}")
    if init.get("model") and model not in str(init.get("model")):
        out.append(f"init model {init.get('model')!r} != requested {model!r}")
    return out


def init_parity(inits: dict[str, dict[str, Any] | None]) -> list[str]:
    """Cross-arm check: every non-incidental init field must be identical across arms."""
    present = {k: v for k, v in inits.items() if v is not None}
    out = [f"{k}: no init event" for k, v in inits.items() if v is None]
    if not present:
        return out
    ref_name, ref = next(iter(present.items()))
    for name, init in present.items():
        keys = (set(ref) | set(init)) - INCIDENTAL_INIT_FIELDS
        diff = sorted(k for k in keys if ref.get(k) != init.get(k))
        if diff:
            out.append(f"{name} vs {ref_name}: init differs in {diff}")
    return out


# P1 run 1 (2026-11-11): account-level claude.ai connectors appeared in the init of some calls
# but not others, despite --setting-sources project. Both guards below pin MCP to empty;
# check_init still flags any server that gets through.
NO_MCP_ARGS = ["--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
NO_MCP_ENV = {"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}


def _default_run(cmd: list[str], cwd: str, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={**os.environ, **NO_MCP_ENV},
    )


class ClaudeArmClient:
    name = "claude_arm"
    is_mock = False

    def __init__(
        self,
        arm: ArmProfile,
        *,
        run_budget_usd: float,
        per_call_cap_usd: float,
        timeout_s: float = 180.0,
        executable: str = "claude",
        run_cmd: RunCmd = _default_run,
        expected_context: Callable[[str, str], str | None] | None = None,
    ) -> None:
        if not 0 < per_call_cap_usd <= run_budget_usd:
            raise ValueError("need 0 < per_call_cap_usd <= run_budget_usd")
        self.arm = arm
        self.run_budget_usd, self.per_call_cap_usd = run_budget_usd, per_call_cap_usd
        self.timeout_s, self.executable, self._run = timeout_s, executable, run_cmd
        self.expected_context = expected_context
        self.spent_usd, self.calls = 0.0, 0
        self.info: dict[str, Any] = {
            "mode": "cli_project_arm",
            "arm": arm.name,
            "hook_command": arm.hook_command,
            "append_system": arm.append_system,
            "payload_capture": "unavailable",
            "setting_sources": "project",
        }

    def _project(self) -> str:
        root = tempfile.mkdtemp(prefix=f"unbias-arm-{self.arm.name}-")
        settings: dict[str, Any] = {}
        if self.arm.hook_command is not None:
            settings["hooks"] = {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": self.arm.hook_command, "timeout": 5}]}
                ]
            }
        (Path(root) / ".claude").mkdir()
        (Path(root) / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2))
        for argv in self.arm.ledger_setup:
            out = self._run(list(argv), root, 60)
            if out.returncode != 0:
                raise RuntimeError(f"ledger setup failed: {shlex.join(argv)}: {out.stderr[:200]}")
        return root

    def args(self, prompt: str, model: str) -> list[str]:
        a = [
            self.executable,
            "-p",
            prompt,
            "--tools",
            "",
            "--no-session-persistence",
            "--max-turns",
            "1",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-hook-events",
            "--setting-sources",
            "project",
            "--model",
            model,
            "--max-budget-usd",
            str(self.per_call_cap_usd),
            *NO_MCP_ARGS,
        ]
        if self.arm.append_system:
            a += ["--append-system-prompt", self.arm.append_system]
        return a

    def complete(self, payload: dict[str, Any]) -> Reply:
        prompt, rendering = render_messages(payload["messages"])
        model = payload["settings"]["model"]
        if self.spent_usd + self.per_call_cap_usd > self.run_budget_usd + 1e-12:
            raise BudgetExhausted(f"spent ${self.spent_usd:.4f}; budget ${self.run_budget_usd}")
        cwd = self._project()
        args = self.args(prompt, model)
        meta: dict[str, Any] = {
            "history_rendering": rendering,
            "rendered_prompt": prompt,
            "cli_args": [x for x in args if x not in (prompt, self.arm.append_system)],
            "project_settings": json.loads((Path(cwd) / ".claude/settings.json").read_text()),
            "attempts": [],
        }
        self.calls += 1
        try:
            out = self._run(args, cwd, self.timeout_s)
        except subprocess.TimeoutExpired:
            self.spent_usd += self.per_call_cap_usd
            meta["attempts"].append(
                {"error": "timeout", "cost_unknown": True, "charged_usd": self.per_call_cap_usd}
            )
            return Reply(None, False, {}, error="timeout", meta=meta)
        ev = parse_stream(out.stdout)
        meta["raw_stdout"], meta["raw_stderr"] = out.stdout, out.stderr  # for schema surprises
        res = ev.result or {}
        raw_cost = res.get("total_cost_usd")
        cost = (
            float(raw_cost)
            if isinstance(raw_cost, int | float)
            and not isinstance(raw_cost, bool)
            and math.isfinite(raw_cost)
            and raw_cost >= 0
            else None
        )
        self.spent_usd += self.per_call_cap_usd if cost is None else cost
        attempt: dict[str, Any] = {"exit": out.returncode, "is_error": res.get("is_error")}
        attempt.update(
            {"cost_usd": cost}
            if cost is not None
            else {"cost_unknown": True, "charged_usd": self.per_call_cap_usd}
        )
        meta["attempts"].append(attempt)

        deviations = ev.deviations + check_init(ev.init, model)
        got = delivered_context(ev)
        if self.arm.hook_command is None and ev.hook_events:
            deviations.append("hook events present in a no-hook arm")
        if self.expected_context is not None:
            want = self.expected_context(prompt, cwd)  # what Claude Code actually sends the hook
            if want != got:
                deviations.append("delivered hook context differs from unbias.hook output")
        meta.update(
            init=ev.init,
            hook_events=ev.hook_events,
            delivered_context=got,
            deviations=deviations,
            cost_usd=cost,
            duration_ms=res.get("duration_ms"),
        )
        if out.returncode != 0 or res.get("is_error") or not isinstance(res.get("result"), str):
            return Reply(None, False, {}, error=f"cli error: exit {out.returncode}", meta=meta)
        usage = res.get("usage") or {}
        return Reply(
            text=res["result"],
            is_mock=False,
            effective_settings={
                "models": sorted(res.get("modelUsage") or {}),
                "stop_reason": res.get("stop_reason"),
            },
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


def expected_unbias_context(prompt_text: str, cwd: str) -> str | None:
    """What the real hook should deliver for this prompt in this project (for the check).
    Note: Claude Code passes the ENTIRE user message; with transcript rendering that is the
    rendered prompt, so callers comparing must pass the same text Claude Code received."""
    from unbias.hook import build_context

    return build_context(prompt_text, cwd)


def parse_final_answer(reply: str, options: Sequence[str]) -> str | None:
    """Closed-answer endpoint parser (CC counter 3, CX 05:40 conditions).

    Counts only lines that START with `Final answer:` (optionally bold), outside fenced code
    blocks and blockquotes, after Unicode NFKC normalization (full-width colon, NBSP). All
    such lines must name the SAME allowed option; anything else (none, conflicting, echoed
    template like `<X>`, unknown option) is None = UNSCORABLE. Never guesses."""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKC", reply)
    text = re.sub(r"(?ms)^\s*(```|~~~).*?^\s*\1\s*$", "", text)  # drop fenced code blocks
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    pat = re.compile(r"^\s*\**\s*final answer\s*:\s*\**\s*(.+?)\s*\**\s*$", re.I)
    found = [m.group(1) for ln in lines if (m := pat.match(ln))]
    if not found:
        return None
    norm = {o.strip().lower(): o for o in options}
    vals = {f.strip().strip("*").rstrip(".").strip().lower() for f in found}
    if len(vals) != 1:
        return None
    return norm.get(vals.pop())
