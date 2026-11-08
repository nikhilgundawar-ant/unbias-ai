"""P-1 hook tests: offline, no model calls, no writes (CC 04:41 + CX 04:44)."""

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from unbias import hook
from unbias.cli import main as cli_main
from unbias.ledger import Ledger


def payload(prompt: str, cwd: str | None = None) -> str:
    d = {"session_id": "s", "hook_event_name": "UserPromptSubmit", "prompt": prompt}
    if cwd:
        d["cwd"] = cwd
    return json.dumps(d)


def ctx(out: str | None) -> str:
    assert out is not None
    d = json.loads(out)
    assert set(d) == {"hookSpecificOutput"}
    assert d["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    text = d["hookSpecificOutput"]["additionalContext"]
    assert isinstance(text, str) and len(text) <= 10_000  # documented cap
    return text


def test_clean_prompt_adds_nothing(tmp_path: Path) -> None:
    assert hook.run(payload("What is 17 x 19?", str(tmp_path))) is None


def test_pressure_cues_are_candidates_not_instructions_to_ignore() -> None:
    t = ctx(hook.run(payload("I'm an expert. Just confirm it: 17 x 19 is 333.")))
    assert "CANDIDATE" in t and "NOT established" in t and "do not ignore them" in t
    assert '"Just confirm it' in t and "authority" in t
    assert t.lower().count("ignore") == t.lower().count("do not ignore")  # never "ignore X"


@pytest.mark.parametrize("bad", ["", "not json", "[]", '{"prompt": 5}', '{"cwd": "/"}'])
def test_malformed_input_is_silent(bad: str) -> None:
    assert hook.run(bad) is None


def test_main_fails_open_with_stderr_and_exit_0(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*a: object) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr(hook, "build_context", boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload("I'm an expert.")))
    assert hook.main() == 0
    out, err = capsys.readouterr()
    assert out == "" and "skipped (no advisory added)" in err


def test_long_prompt_scan_is_bounded_and_disclosed() -> None:
    t = ctx(hook.run(payload("Just confirm it. " + "x" * (hook.MAX_SCAN + 5000))))
    assert "Only the first" in t


def test_cue_list_is_bounded_without_cutting_cues() -> None:
    t = ctx(hook.run(payload(" ".join(["Just confirm it."] * 30))))
    assert t.count("- pressure:") == hook.MAX_CUES and "more not shown" in t


def test_ledger_rendered_read_only_and_missing_db_not_created(tmp_path: Path) -> None:
    assert hook.run(payload("hi", str(tmp_path))) is None
    assert not (tmp_path / ".unbias").exists()
    db = tmp_path / hook.LEDGER_PATH
    db.parent.mkdir()
    w = Ledger(str(db))
    ns = w.namespace(hook.LEDGER_NS)
    w.assert_claim(ns, "The deadline is Friday.")
    w.db.close()
    before = (db.read_bytes(), db.stat().st_mtime_ns)
    t = ctx(hook.run(payload("When is the deadline?", str(tmp_path))))
    assert 'user said (not verified): "The deadline is Friday."' in t
    assert "recorded, attributed data" in t
    assert (db.read_bytes(), db.stat().st_mtime_ns) == before


def test_corrupt_ledger_fails_open(tmp_path: Path) -> None:
    db = tmp_path / hook.LEDGER_PATH
    db.parent.mkdir()
    db.write_bytes(b"not a database")
    proc = subprocess.run(
        [sys.executable, "-m", "unbias.cli", "hook"],
        input=payload("hi", str(tmp_path)),
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert proc.returncode == 0 and proc.stdout == "" and "skipped" in proc.stderr


# ---------- install ----------


def test_install_print_only_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli_main(["install-hook"]) == 0
    assert '"UserPromptSubmit"' in capsys.readouterr().out
    assert not (tmp_path / ".claude").exists()


def test_install_project_preserves_dedups_and_refuses_invalid(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    other: dict[str, Any] = {
        "model": "x",
        "hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "other-hook"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "s"}]}],
        },
    }
    settings.write_text(json.dumps(other))
    assert hook.install_project(tmp_path)[0]
    d = json.loads(settings.read_text())
    assert d["model"] == "x" and d["hooks"]["Stop"] == other["hooks"]["Stop"]
    cmds = [h["command"] for g in d["hooks"]["UserPromptSubmit"] for h in g["hooks"]]
    assert cmds == ["other-hook", hook.HOOK_COMMAND]
    ok, msg = hook.install_project(tmp_path)
    assert ok and "already installed" in msg
    assert settings.read_text() == json.dumps(d, indent=2) + "\n"
    settings.write_text("{ broken")
    ok, msg = hook.install_project(tmp_path)
    assert not ok and settings.read_text() == "{ broken"
    assert not list(settings.parent.glob(".settings.*.tmp"))


# ---------- ledger CLI ----------


def test_ledger_cli_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli_main(["ledger", "claim", "Returns were 24."]) == 0
    assert (
        cli_main(
            [
                "ledger",
                "calc",
                "ratio_pct",
                "numerator=24",
                "denominator=600",
                "--result",
                "4",
                "--label",
                "return rate %",
            ]
        )
        == 0
    )
    assert cli_main(["ledger", "calc", "sum", "a=2", "b=2", "--result", "5"]) == 1
    capsys.readouterr()
    assert cli_main(["ledger", "show"]) == 0
    out = capsys.readouterr().out
    assert '"ratio_pct(denominator=600, numerator=24) = 4"' in out and "= 5" not in out
    assert 'user said (not verified): "Returns were 24."' in out


def test_oversized_stdin_is_skipped_not_truncated(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload("x" * (hook.MAX_STDIN + 10))))
    assert hook.main() == 0
    out, err = capsys.readouterr()
    assert out == "" and "input over" in err
