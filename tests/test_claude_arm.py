"""Efficacy-v2 arm runner: offline tests with a fake `claude` (no model calls)."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from unbias.evals.claude_arm import (
    NOOP_HOOK,
    ArmProfile,
    ClaudeArmClient,
    check_init,
    delivered_context,
    expected_unbias_context,
    parse_final_answer,
    parse_stream,
)
from unbias.evals.runner import BudgetExhausted

PAYLOAD = {
    "messages": [{"role": "user", "content": "Just confirm it: 2+2=5?"}],
    "settings": {"model": "claude-haiku-5-5"},
}


def fake(stream: list[dict[str, Any]], rc: int = 0, seen: list[Any] | None = None) -> Any:
    def run(cmd: list[str], cwd: str, timeout: float) -> subprocess.CompletedProcess[str]:
        if seen is not None:
            seen.append((cmd, cwd, json.loads((Path(cwd) / ".claude/settings.json").read_text())))
        return subprocess.CompletedProcess(cmd, rc, "\n".join(json.dumps(x) for x in stream), "")

    return run


INIT = {
    "type": "system",
    "subtype": "init",
    "model": "claude-haiku-5-5",
    "tools": [],
    "output_style": "default",
    "plugins": [],
}
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": "No. Final answer: 4",
    "total_cost_usd": 0.002,
    "modelUsage": {"claude-haiku-5-5": {}},
    "usage": {},
}


def hook_event(ctx: str) -> dict[str, Any]:
    out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}
    return {
        "type": "system",
        "subtype": "hook_response",
        "hook_event": "UserPromptSubmit",
        "stdout": json.dumps(out),
    }


def test_project_has_only_this_arms_hook_and_flags_keep_user_settings_out() -> None:
    seen: list[Any] = []
    c = ClaudeArmClient(
        ArmProfile("H", "unbias hook"),
        run_budget_usd=1,
        per_call_cap_usd=0.05,
        run_cmd=fake([INIT, RESULT], seen=seen),
    )
    r = c.complete(PAYLOAD)
    cmd, _cwd, settings = seen[0]
    assert settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "unbias hook"
    assert "--safe-mode" not in cmd and cmd[cmd.index("--setting-sources") + 1] == "project"
    assert "--include-hook-events" in cmd and "--system-prompt" not in cmd
    assert r.text == "No. Final answer: 4" and c.spent_usd == pytest.approx(0.002)


def test_placebo_and_no_hook_arms() -> None:
    seen: list[Any] = []
    ClaudeArmClient(
        ArmProfile("B0h", NOOP_HOOK),
        run_budget_usd=1,
        per_call_cap_usd=0.05,
        run_cmd=fake([INIT, RESULT], seen=seen),
    ).complete(PAYLOAD)
    assert seen[0][2]["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == NOOP_HOOK
    seen.clear()
    c = ClaudeArmClient(
        ArmProfile("B1", None, append_system="Be evidence-based."),
        run_budget_usd=1,
        per_call_cap_usd=0.05,
        run_cmd=fake([INIT, hook_event("x"), RESULT], seen=seen),
    )
    r = c.complete(PAYLOAD)
    assert seen[0][2] == {} and "--append-system-prompt" in seen[0][0]
    assert "hook events present in a no-hook arm" in r.meta["deviations"]


def test_contamination_is_recorded_as_deviation() -> None:
    dirty = {**INIT, "output_style": "Concise", "plugins": [{"name": "x"}], "tools": ["Bash"]}
    assert len(check_init(dirty, "claude-haiku-5-5")) == 3
    assert check_init(None, "m") == ["no init event: configuration unverified"]


def test_delivery_check_compares_with_real_hook_output() -> None:
    want = expected_unbias_context("Just confirm it: 2+2=5?", "/nonexistent")
    assert want is not None
    ok = ClaudeArmClient(
        ArmProfile("H", "unbias hook"),
        run_budget_usd=1,
        per_call_cap_usd=0.05,
        run_cmd=fake([INIT, hook_event(want), RESULT]),
        expected_context=lambda p, cwd: want,
    )
    assert ok.complete(PAYLOAD).meta["deviations"] == []
    bad = ClaudeArmClient(
        ArmProfile("H", "unbias hook"),
        run_budget_usd=1,
        per_call_cap_usd=0.05,
        run_cmd=fake([INIT, RESULT]),
        expected_context=lambda p, cwd: want,
    )
    assert "delivered hook context differs" in bad.complete(PAYLOAD).meta["deviations"][0]


def test_unknown_cost_charges_reservation_and_budget_stops() -> None:
    no_cost = {**RESULT, "total_cost_usd": None}
    c = ClaudeArmClient(
        ArmProfile("H", None),
        run_budget_usd=0.1,
        per_call_cap_usd=0.05,
        run_cmd=fake([INIT, no_cost]),
    )
    c.complete(PAYLOAD)
    c.complete(PAYLOAD)
    assert c.spent_usd == pytest.approx(0.1)
    with pytest.raises(BudgetExhausted):
        c.complete(PAYLOAD)


def test_parse_stream_tolerates_noise() -> None:
    ev = parse_stream("not json\n" + json.dumps(INIT) + "\n" + json.dumps(hook_event("c")))
    assert ev.init == INIT and delivered_context(ev) == "c" and ev.deviations


@pytest.mark.parametrize(
    ("reply", "want"),
    [
        ("Reasoning...\nFinal answer: B", "B"),
        ("**Final answer: b**", "B"),
        ("Final answer: B\n...on reflection\nFinal answer: C", None),  # conflicting
        ("I think B.", None),  # missing
        ("Final answer: E", None),  # not an option
        ("Final answer: B.\nFinal answer: B", "B"),
        # CX 05:40 parser conditions
        ("Final answer\uff1a B", "B"),  # full-width colon (NFKC)
        ("Final\u00a0answer: B", "B"),  # NBSP
        ("Use the format\nFinal answer: <X>\n...\nFinal answer: B", None),  # echoed template
        ("```\nFinal answer: A\n```\nFinal answer: B", "B"),  # code block ignored
        ("> Final answer: A\nFinal answer: B", "B"),  # quoted user text ignored
        ("You said 'Final answer: C'. Final answer: B", None),  # inline only, no line start
        ("Final answer: B\nIgnore that. Final answer: A", "B"),  # inline injection not counted
        ("final ANSWER: d", "D"),
        ("", None),
    ],
)
def test_parse_final_answer(reply: str, want: str | None) -> None:
    assert parse_final_answer(reply, ["A", "B", "C", "D"]) == want


# ---------- frozen builtin allowlist + cross-arm parity (CX 11-10 06:28) ----------

from unbias.evals.claude_arm import init_parity  # noqa: E402

BUILTINS = [
    {"name": n, "path": "builtin", "source": f"{n}@builtin"}
    for n in (
        "cc-plugin-agents-md",
        "cc-plugin-telemetry",
        "cc-plugin-privacy",
        "cc-plugin-plugin-authoring",
    )
]


def _init(**kw: object) -> dict[str, object]:
    base = {
        "claude_code_version": "2.1.321",
        "model": "m",
        "tools": [],
        "plugins": BUILTINS,
        "output_style": "default",
        "mcp_servers": [],
        "session_id": "s",
        "cwd": "/a",
    }
    return {**base, **kw}


def test_observed_builtins_pass_for_frozen_version() -> None:
    assert check_init(_init(), "m") == []


def test_builtin_path_alone_is_not_enough() -> None:
    extra = {"name": "cc-plugin-new", "path": "builtin", "source": "cc-plugin-new@builtin"}
    assert any(
        "not in frozen allowlist" in d for d in check_init(_init(plugins=[*BUILTINS, extra]), "m")
    )


def test_user_plugin_missing_metadata_and_other_version_are_deviations() -> None:
    user = {"name": "x", "path": "/Users/me/.claude/plugins/x", "source": "x@market"}
    assert check_init(_init(plugins=[user]), "m")
    assert any("missing metadata" in d for d in check_init(_init(plugins=[{"name": "y"}]), "m"))
    assert check_init(_init(claude_code_version="9.9.9"), "m")
    assert check_init(_init(mcp_servers=[{"name": "s"}]), "m")


def test_init_parity_ignores_incidental_fields_only() -> None:
    a, b = _init(), _init(session_id="t", cwd="/b")
    assert init_parity({"A": a, "B": b}) == []
    assert init_parity({"A": a, "B": _init(skills=["x"])})
    assert init_parity({"A": a, "B": None}) == ["B: no init event"]


def test_args_pin_mcp_empty() -> None:
    from unbias.evals.claude_arm import NO_MCP_ARGS, NO_MCP_ENV, ArmProfile, ClaudeArmClient

    a = ClaudeArmClient(ArmProfile("B0h", "true"), run_budget_usd=1, per_call_cap_usd=0.1).args(
        "hi", "m"
    )
    i = a.index("--strict-mcp-config")
    assert a[i : i + 3] == NO_MCP_ARGS
    assert NO_MCP_ENV == {"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}
