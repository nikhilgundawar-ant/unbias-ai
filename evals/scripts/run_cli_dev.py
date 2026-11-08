"""Dev-only CLI baseline run (D16).
Usage: PYTHONPATH=src uv run python evals/scripts/run_cli_dev.py [model] [fixture.jsonl]"""

import sys
from pathlib import Path

from unbias.evals.claude_cli import ClaudeCliClient
from unbias.evals.fixtures import check_families, load_families
from unbias.evals.runner import GenerationSettings, cli_baseline_arms, load_run, run_baselines

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "evals/fixtures/schema.json"

model = sys.argv[1] if len(sys.argv) > 1 else "claude-sonnet-5-5"
FIXTURES = ROOT / (sys.argv[2] if len(sys.argv) > 2 else "evals/fixtures/seed_dev.jsonl")
BUDGET = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
PER_CALL = float(sys.argv[4]) if len(sys.argv) > 4 else 0.10
fams = load_families(FIXTURES)
check_families(fams, SCHEMA)
client = ClaudeCliClient(run_budget_usd=BUDGET, per_call_cap_usd=PER_CALL, timeout_s=300)
run_dir = run_baselines(
    fams,
    client,
    GenerationSettings(model=model),
    ROOT / "evals/runs",
    fixture_path=FIXTURES,
    schema_path=SCHEMA,
    arms=cli_baseline_arms(),
    order_seed=20261107,
)
manifest, records = load_run(run_dir)
errors = sum(1 for r in records if r["error"])
print(f"run_dir={run_dir}\nrecords={len(records)} errors={errors} aborted={manifest['aborted']}")
print(f"spent_usd={client.spent_usd:.4f} calls={client.calls}")
models = sorted({m for r in records for m in r["effective_settings"].get("models", [])})
print(f"resolved_models={models}")
