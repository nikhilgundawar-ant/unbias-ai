"""RS-1 real-life simulated evals (CX 18:39 corrections a-d).

  freeze          encode CX specs, validate, write evals/plans/rs1_plan.json (no calls)
  run <plan_sha>  verify frozen plan, then run BOTH models with ONE shared client
                  ($3.00 global cap incl. retries, $0.05/call). No reruns on weak results.
Usage: PYTHONPATH=src uv run python evals/scripts/run_rs1.py freeze|run <sha>
"""

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evals/scripts"))

from encode_rs1_specs import OUT as FIXTURE  # noqa: E402
from encode_rs1_specs import SRC as SPECS  # noqa: E402
from encode_rs1_specs import main as encode_main  # noqa: E402

from unbias.evals.fixtures import check_families, load_families  # noqa: E402
from unbias.evals.runner import (  # noqa: E402
    BudgetExhausted,
    GenerationSettings,
    ModelUnavailable,
    _sha256,
    cli_baseline_arms,
    load_run,
    run_baselines,
)

SCHEMA = ROOT / "evals/fixtures/schema.json"
PLAN = ROOT / "evals/plans/rs1_plan.json"
MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")
BUDGET, PER_CALL, SEED = 3.00, 0.05, 20261108
EXCLUDED: dict[str, str] = {}  # family_id -> reason; filled only by CC/CX agreement


def h(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def freeze() -> None:
    encode_main()
    fams = [f for f in load_families(FIXTURE) if f["family_id"] not in EXCLUDED]
    check_families(fams, SCHEMA)
    arms = cli_baseline_arms()
    n_var = sum(len(f["variants"]) for f in fams)
    plan = {
        "plan": "RS-1 real-life simulated scenarios (dev-only; user request 2026-11-08)",
        "measures": "A0 vs A1 = system prompting only; no neutralizer/ledger wrapper claim",
        "metrics": {
            "neutral/authority/emotional": "hold vs cave after a correct seeded answer",
            "valid_correction": "M11 responsiveness to supplied new evidence (own denominator)",
        },
        "scorer": "extract_number_stance (abstains when uncertain); unscorable kept + shown",
        "models": list(MODELS),
        "arms": [a.name for a in arms],
        "arm_system_sha256": {a.name: _sha256(a.system) for a in arms},
        "generation_settings": {m: asdict(GenerationSettings(model=m)) for m in MODELS},
        "scorer_sha256": h(ROOT / "src/unbias/evals/extractors.py"),
        "report_script_sha256": h(ROOT / "evals/scripts/report_rs1.py"),
        "excluded_families": EXCLUDED,
        "reporting": "neutral recheck reported separately from authority/emotional pressure; "
        "valid_correction split into evidence vs preference (rs1_cx12) subsets",
        "families": len(fams),
        "variants": n_var,
        "planned_calls": n_var * len(arms) * len(MODELS),
        "global_budget_usd": BUDGET,
        "per_call_cap_usd": PER_CALL,
        "shared_client_across_models": True,
        "order_seed": SEED,
        "no_reruns": True,
        "specs_sha256": h(SPECS),
        "fixture_sha256": h(FIXTURE),
        "schema_sha256": h(SCHEMA),
    }
    PLAN.write_text(json.dumps(plan, indent=2) + "\n")
    print(f"planned_calls={plan['planned_calls']} plan_sha256={h(PLAN)}")


def run(expected: str) -> None:
    from unbias.evals.claude_cli import ClaudeCliClient

    if h(PLAN) != expected:
        sys.exit("plan changed since it was frozen")
    plan = json.loads(PLAN.read_text())
    for key, p in (("specs_sha256", SPECS), ("fixture_sha256", FIXTURE), ("schema_sha256", SCHEMA)):
        if h(p) != plan[key]:
            sys.exit(f"{key} drift")
    if h(ROOT / "src/unbias/evals/extractors.py") != plan["scorer_sha256"]:
        sys.exit("scorer drift")
    arms = cli_baseline_arms()
    if {a.name: _sha256(a.system) for a in arms} != plan["arm_system_sha256"]:
        sys.exit("arm system prompt drift")
    for m in plan["models"]:
        if asdict(GenerationSettings(model=m)) != plan["generation_settings"][m]:
            sys.exit("generation settings drift")
    fams = [f for f in load_families(FIXTURE) if f["family_id"] not in plan["excluded_families"]]
    check_families(fams, SCHEMA)
    client = ClaudeCliClient(
        run_budget_usd=plan["global_budget_usd"],
        per_call_cap_usd=plan["per_call_cap_usd"],
        timeout_s=300,
    )
    runs = []
    for model in plan["models"]:
        try:
            run_dir = run_baselines(
                fams,
                client,
                GenerationSettings(model=model),
                ROOT / "evals/runs",
                fixture_path=FIXTURE,
                schema_path=SCHEMA,
                arms=arms,
                order_seed=plan["order_seed"],
            )
        except (BudgetExhausted, ModelUnavailable) as e:
            print(f"{model}: stopped: {e}")
            break
        manifest, records = load_run(run_dir)
        errors = sum(1 for r in records if r["error"])
        runs.append({"model": model, "run_dir": run_dir.name, "aborted": manifest["aborted"]})
        print(
            f"{model}: {run_dir.name} records={len(records)} errors={errors} "
            f"aborted={manifest['aborted']} cumulative_usd={client.spent_usd:.4f}"
        )
        if manifest["aborted"]:
            break
    index = {
        "plan_sha256": expected,
        "runs": runs,
        "spent_usd_estimate": client.spent_usd,
        "calls": client.calls,
    }
    (ROOT / "evals/plans/rs1_runs.json").write_text(json.dumps(index, indent=2) + "\n")


if __name__ == "__main__":
    if sys.argv[1:2] == ["freeze"]:
        freeze()
    elif sys.argv[1:2] == ["run"] and len(sys.argv) == 3:
        run(sys.argv[2])
    else:
        sys.exit(__doc__)
