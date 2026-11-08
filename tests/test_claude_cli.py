import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from unbias.evals.claude_cli import ClaudeCliClient, render_messages
from unbias.evals.fixtures import load_families
from unbias.evals.runner import (
    ANTI_SYCOPHANCY_PROMPT,
    BudgetExhausted,
    GenerationSettings,
    cli_baseline_arms,
    load_run,
    run_baselines,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals/fixtures/seed_dev.jsonl"
SCHEMA = ROOT / "evals/fixtures/schema.json"
SETTINGS = GenerationSettings(model="claude-test", max_tokens=256)


def fake_cli_unavailable() -> Any:
    def run(cmd: list[str], cwd: str, timeout: float) -> subprocess.CompletedProcess[str]:
        if cmd[1:] == ["--version"]:
            return subprocess.CompletedProcess(cmd, 0, "9.9.9\n", "")
        body = {
            "type": "result",
            "subtype": "error",
            "is_error": True,
            "api_error_status": 404,
            "result": "model: claude-nope not found",
            "total_cost_usd": 0,
        }
        return subprocess.CompletedProcess(cmd, 1, json.dumps(body), "")

    return run


def fake_cli(
    cost: Any = 0.001,
    result: Any = "323",
    fail_times: int = 0,
    exit_code: int = 0,
    drop_cost: bool = False,
) -> Any:
    calls: list[list[str]] = []
    state = {"fails": fail_times}

    def run(cmd: list[str], cwd: str, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[1:] == ["--version"]:
            return subprocess.CompletedProcess(cmd, 0, "9.9.9 (Claude Code)\n", "")
        if state["fails"] > 0:
            state["fails"] -= 1
            raise subprocess.TimeoutExpired(cmd, timeout)
        body = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": result,
            "total_cost_usd": cost,
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 2, "output_tokens": 5},
            "modelUsage": {"claude-test": {}},
        }
        if drop_cost:
            body.pop("total_cost_usd")
        return subprocess.CompletedProcess(cmd, exit_code, json.dumps(body), "")

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_render_single_and_transcript() -> None:
    assert render_messages([{"role": "user", "content": "hi"}]) == ("hi", "single_turn")
    text, mode = render_messages(
        [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "323"},
            {"role": "user", "content": "no, 333"},
        ]
    )
    assert mode == "transcript"
    assert "[Assistant]: 323" in text and text.endswith("[User, new message]: no, 333")


def test_safe_flags_and_no_bypass() -> None:
    run = fake_cli()
    c = ClaudeCliClient(run_cmd=run)
    r = c.complete(
        {"messages": [{"role": "user", "content": "x"}], "settings": {"model": "m"}, "system": "S"}
    )
    cmd = run.calls[-1]
    assert r.text == "323" and not r.is_mock
    for flag in ("--safe-mode", "--no-session-persistence", "--max-budget-usd"):
        assert flag in cmd
    assert cmd[cmd.index("--tools") + 1] == ""
    assert not any("dangerously" in a or "bypass" in a for a in cmd)
    assert r.meta["payload_capture"] == "unavailable" and c.info["cli_version"].startswith("9.9.9")


def test_budget_reservation_stops_before_overspend() -> None:
    c = ClaudeCliClient(run_budget_usd=0.1, per_call_cap_usd=0.05, run_cmd=fake_cli(cost=0.04))
    p = {"messages": [{"role": "user", "content": "x"}], "settings": {"model": "m"}}
    c.complete(p)  # spent 0.04; next reservation 0.09 <= 0.1
    c.complete(p)  # spent 0.08; next reservation 0.13 > 0.1
    with pytest.raises(BudgetExhausted):
        c.complete(p)


def test_timeout_is_retried_charged_and_recorded() -> None:
    c = ClaudeCliClient(max_retries=1, run_cmd=fake_cli(fail_times=5))
    r = c.complete({"messages": [{"role": "user", "content": "x"}], "settings": {"model": "m"}})
    assert r.text is None and r.error and "timeout" in r.error
    assert len(r.meta["attempts"]) == 2 and c.spent_usd == pytest.approx(0.10)


def test_cli_run_manifest_interleaving_and_abort(tmp_path: Path) -> None:
    fams = load_families(FIXTURES)
    client = ClaudeCliClient(run_budget_usd=0.2, per_call_cap_usd=0.05, run_cmd=fake_cli(cost=0.05))
    run_dir = run_baselines(
        fams,
        client,
        SETTINGS,
        tmp_path,
        fixture_path=FIXTURES,
        schema_path=SCHEMA,
        arms=cli_baseline_arms(),
        order_seed=3,
    )
    manifest, records = load_run(run_dir)
    assert manifest["aborted"] and manifest["aborted"].startswith("budget")
    assert len(records) == 4 and manifest["client_info"]["mode"] == "cli_headless"
    a1 = next(a for a in manifest["arms"] if a["name"].startswith("A1"))
    assert a1["system"] == ANTI_SYCOPHANCY_PROMPT and len(a1["system_sha256"]) == 64


def test_arm_order_is_randomized_but_seeded(tmp_path: Path) -> None:
    fams = load_families(FIXTURES)

    def orders(seed: int, sub: str) -> list[str]:
        client = ClaudeCliClient(run_budget_usd=100, per_call_cap_usd=0.05, run_cmd=fake_cli())
        d = run_baselines(
            fams,
            client,
            SETTINGS,
            tmp_path / sub,
            fixture_path=FIXTURES,
            schema_path=SCHEMA,
            arms=cli_baseline_arms(),
            order_seed=seed,
        )
        _, recs = load_run(d)
        return [r["arm"] for r in recs if r["arm_order_index"] == 0]

    first = orders(1, "a")
    assert first == orders(1, "b")  # reproducible
    assert len(set(first)) == 2  # both arms go first sometimes


P = {"messages": [{"role": "user", "content": "x"}], "settings": {"model": "m"}}


@pytest.mark.parametrize(
    "kwargs",
    [{"drop_cost": True}, {"cost": float("nan")}, {"cost": -1.0}, {"cost": "0.01"}, {"cost": None}],
    ids=["missing", "nan", "negative", "string", "null"],
)
def test_unknown_cost_charges_full_reservation_cx_13_41(kwargs: dict[str, Any]) -> None:
    # CX 13:41 counterexample: missing cost must not be accounted as $0.
    c = ClaudeCliClient(run_budget_usd=0.10, per_call_cap_usd=0.05, run_cmd=fake_cli(**kwargs))
    r1 = c.complete(P)
    assert r1.meta["cost_unknown"] and c.spent_usd == pytest.approx(0.05)
    c.complete(P)
    with pytest.raises(BudgetExhausted):
        c.complete(P)  # third call cannot start: 0.10 already charged


def test_nonzero_exit_is_error_but_cost_still_counted() -> None:
    c = ClaudeCliClient(max_retries=0, run_cmd=fake_cli(cost=0.01, exit_code=1))
    r = c.complete(P)
    assert r.text is None and r.error and "exit 1" in r.error and c.spent_usd == pytest.approx(0.01)


def test_cost_above_cap_is_recorded_actual_and_flagged() -> None:
    c = ClaudeCliClient(run_budget_usd=1.0, per_call_cap_usd=0.05, run_cmd=fake_cli(cost=0.2))
    r = c.complete(P)
    assert r.meta["attempts"][0]["cost_exceeded_cap"] and c.spent_usd == pytest.approx(0.2)


def test_attempts_survive_budget_exhaustion_mid_retry(tmp_path: Path) -> None:
    # First attempt times out (charged 0.05); the retry cannot be reserved -> partial is recorded.
    client = ClaudeCliClient(
        run_budget_usd=0.09, per_call_cap_usd=0.05, max_retries=1, run_cmd=fake_cli(fail_times=9)
    )
    fams = load_families(FIXTURES)[:1]
    run_dir = run_baselines(
        fams,
        client,
        SETTINGS,
        tmp_path,
        fixture_path=FIXTURES,
        schema_path=SCHEMA,
        arms=cli_baseline_arms(),
    )
    manifest, records = load_run(run_dir)
    assert manifest["aborted"] and len(records) == 1
    assert records[0]["error"].startswith("budget exhausted")
    assert len(records[0]["client_meta"]["attempts"]) == 1


def test_unsupported_model_stops_run_without_substitution(tmp_path: Path) -> None:
    client = ClaudeCliClient(run_cmd=fake_cli_unavailable())
    run_dir = run_baselines(
        load_families(FIXTURES),
        client,
        GenerationSettings(model="claude-nope"),
        tmp_path,
        fixture_path=FIXTURES,
        schema_path=SCHEMA,
        arms=cli_baseline_arms(),
    )
    manifest, records = load_run(run_dir)
    assert manifest["aborted"].startswith("model unavailable") and len(records) == 1
    assert records[0]["error"].startswith("model unavailable")  # attempted call is recorded
    assert client.calls == 1  # one request, not 120


def test_ambiguous_first_failures_stop_run(tmp_path: Path) -> None:
    client = ClaudeCliClient(max_retries=0, run_cmd=fake_cli(cost=0.0, exit_code=1))
    run_dir = run_baselines(
        load_families(FIXTURES),
        client,
        SETTINGS,
        tmp_path,
        fixture_path=FIXTURES,
        schema_path=SCHEMA,
        arms=cli_baseline_arms(),
    )
    manifest, records = load_run(run_dir)
    assert manifest["aborted"].startswith("first 2 calls failed") and len(records) == 2


def test_answer_text_about_availability_is_data_not_control_cx_15_09() -> None:
    c = ClaudeCliClient(run_cmd=fake_cli(result="That model is not available offline."))
    r = c.complete(P)
    assert r.text == "That model is not available offline." and r.error is None


def test_timeout_end_to_end_reported_as_unknown_cost(tmp_path: Path) -> None:
    from unbias.cli import build_report

    client = ClaudeCliClient(
        run_budget_usd=0.2, per_call_cap_usd=0.05, max_retries=0, run_cmd=fake_cli(fail_times=1)
    )
    run_dir = run_baselines(
        load_families(FIXTURES)[:1],
        client,
        SETTINGS,
        tmp_path,
        fixture_path=FIXTURES,
        schema_path=SCHEMA,
        arms=cli_baseline_arms(),
    )
    assert "Unknown-cost attempts: 1 (reserved $0.0500" in build_report(run_dir)


def test_legacy_reservation_without_flag_counts_as_unknown() -> None:
    from unbias.cli import _cost

    rec = {"client_meta": {"attempts": [{"error": "timeout", "charged_usd": 0.05}]}}
    assert _cost([rec]) == (0.0, 1, 0.05, 1)
