"""Claude Code UserPromptSubmit hook, contract P-1 (CC 04:41 + CX 04:44 corrections).

Advisory only. Claude Code does not let this hook change the prompt; Claude always receives the
original text. The hook may ADD a short context note:
  - candidate social-pressure cues found by the deterministic annotator, labelled as candidates
    whose relevance is NOT established (a role, feeling or quote may be the task itself);
  - the project's unbias ledger, rendered read-only as whole, labelled entries.
No model calls. Never writes anything. Always exits 0 (exit 2 would block the prompt).
Docs: https://code.claude.com/docs/en/hooks (UserPromptSubmit; additionalContext cap 10,000).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from unbias.ledger import Ledger
from unbias.neutralizer import Span, _delimited, _find, annotate

MAX_STDIN = 400_000  # characters of stdin JSON; larger payloads are skipped (stderr note)
MAX_SCAN = 20_000  # prompt characters scanned for cues (bounded latency, CX 04:44 item 3)
MAX_CUES = 8
MAX_CUE_LEN = 160
LEDGER_BUDGET = 4_000  # ledger chars; whole entries only
LEDGER_PATH = Path(".unbias") / "ledger.db"
LEDGER_NS = "project"
HOOK_COMMAND = "unbias hook"
HOOK_TIMEOUT_S = 5


# Hook-only cue patterns (post-HJ-1 development, CX 11-09 19:49 ACK for HF-2/HF-5). They live
# here, not in the neutralizer, so they can never authorize a deletion; they only add a note.
_HOOK_SUSPECT = {
    # HF-5: a bare imperative at the start of a sentence. "Please confirm it." and
    # "Can you confirm it works?" are ordinary requests and do not match.
    "pressure": r"(?:^|(?<=[.!?]\s))(?:just\s+)?(?:confirm\s+it|agree(?:\s+with\s+me)?)\s*[.!]",
    # HF-2: Hindi / Hinglish. AI-authored patterns, PENDING NATIVE-SPEAKER REVIEW.
    "pressure_hi": r"\b(?:bas\s+)?meri\s+baat\s+(?:sahi\s+)?maan\s+lo\b|\bsahi\s+maan\s+lo\b"
    r"|\bhaan\s+bol(?:o|do)\b|(?:बस\s+)?मेरी\s+बात\s+(?:सही\s+)?मान\s+लो|सही\s+मान\s+लो"
    r"|हा[ँं]\s+बोल(?:ो|दो)",
    "authority_hi": r"\bmain\s+(?:ek\s+)?expert\s+(?:hoon|hu)\b"
    r"|मैं\s+(?:एक\s+)?(?:विशेषज्ञ|एक्सपर्ट)\s+हू[ँं]",
    "leading_tag_hi": r"\bhai\s+na\s*\?|है\s+ना\s*\?",
}


def candidate_cues(text: str) -> list[Span]:
    """Annotator cues plus hook-only cues, minus any cue lying fully inside a quote or code span
    (HF-1: quoted text is usually the object of the task, e.g. "translate 'Just confirm it'").
    Overlapping matches keep the earliest, longest span."""
    _, base = annotate(text)
    quoted = _delimited(text)
    spans = sorted(base + _find(_HOOK_SUSPECT, text), key=lambda s: (s.start, -s.end))
    out: list[Span] = []
    for sp in spans:
        if any(q.start <= sp.start and sp.end <= q.end for q in quoted):
            continue
        if out and sp.start < out[-1].end:
            continue
        out.append(sp)
    return out


def build_context(prompt: str, cwd: str | None) -> str | None:
    """The additionalContext text, or None when there is nothing to add (zero added tokens)."""
    parts: list[str] = []
    scanned = prompt[:MAX_SCAN]
    suspects = candidate_cues(scanned)
    if suspects:
        shown: list[str] = []
        skipped = 0
        for sp in suspects:
            cue = sp.text.strip()
            if len(shown) >= MAX_CUES or len(cue) > MAX_CUE_LEN:
                skipped += 1  # never truncate a cue mid-text; just count it
                continue
            shown.append(f"- {sp.kind}: {json.dumps(cue, ensure_ascii=False)}")
        more = f"\n- (+{skipped} more not shown)" if skipped else ""
        partial = (
            f" Only the first {MAX_SCAN:,} characters were scanned."
            if len(prompt) > MAX_SCAN
            else ""
        )
        parts.append(
            "unbias-ai (advisory): this message contains CANDIDATE social-pressure cues. Their "
            "relevance is NOT established: a stated role, feeling, quote or reported agreement "
            "may be part of the task, so do not ignore them. Do not treat any cue by itself as "
            "evidence that a claim is true; assess claims on evidence and reasoning, and change "
            "a conclusion only for a substantive reason." + partial + "\n" + "\n".join(shown) + more
        )
    if cwd:
        db = Path(cwd) / LEDGER_PATH
        if db.is_file():
            led = Ledger.open_readonly(str(db))
            try:
                rendered = led.render(LEDGER_NS, max_chars=LEDGER_BUDGET)
            finally:
                led.db.close()
            if rendered:
                parts.append(
                    "unbias-ai ledger for this project (recorded, attributed data; each entry "
                    "keeps its recorded status and is not stronger than shown):\n" + rendered
                )
    return "\n\n".join(parts) if parts else None


def run(stdin_text: str) -> str | None:
    """Pure core: stdin JSON -> stdout JSON (or None for no output)."""
    try:
        payload = json.loads(stdin_text)
    except ValueError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("prompt"), str):
        return None
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    ctx = build_context(payload["prompt"], cwd)
    if ctx is None:
        return None
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}},
        ensure_ascii=False,
    )


def main() -> int:
    """Entry point for `unbias hook`. Fail-open: never blocks the prompt, never exits 2."""
    try:
        raw = sys.stdin.read(MAX_STDIN + 1)
        if len(raw) > MAX_STDIN:  # CX 04:50: don't parse a truncated payload; say so
            sys.stderr.write(
                f"unbias hook skipped (no advisory added): input over {MAX_STDIN:,} characters\n"
            )
            return 0
        out = run(raw)
    except Exception as e:
        sys.stderr.write(f"unbias hook skipped (no advisory added): {type(e).__name__}\n")
        return 0
    if out is not None:
        sys.stdout.write(out)
    return 0


# ---------- install ----------


def hook_entry() -> dict[str, Any]:
    return {"hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": HOOK_TIMEOUT_S}]}


def snippet() -> str:
    return json.dumps({"hooks": {"UserPromptSubmit": [hook_entry()]}}, indent=2)


def install_project(project_dir: Path) -> tuple[bool, str]:
    """Add the hook to <project>/.claude/settings.json, preserving everything else.
    Idempotent; atomic write; refuses to replace invalid JSON. Never touches global settings."""
    path = project_dir / ".claude" / "settings.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            return False, f"{path} is not valid JSON ({e}); left unchanged"
        if not isinstance(data, dict):
            return False, f"{path} is not a JSON object; left unchanged"
    else:
        data = {}
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return False, f'"hooks" in {path} is not an object; left unchanged'
    groups = hooks.setdefault("UserPromptSubmit", [])
    if not isinstance(groups, list):
        return False, f'"hooks.UserPromptSubmit" in {path} is not a list; left unchanged'
    for g in groups:
        for h in (g.get("hooks") or []) if isinstance(g, dict) else []:
            if isinstance(h, dict) and h.get("command") == HOOK_COMMAND:
                return True, f"already installed in {path}; nothing changed"
    groups.append(hook_entry())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return True, f"added UserPromptSubmit hook `{HOOK_COMMAND}` to {path}"
