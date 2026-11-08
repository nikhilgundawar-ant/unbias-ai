"""CAL-1 step 2: run the Sonnet grader over the frozen packet (39 calls, cap $1.50). Outputs are
frozen with a hash BEFORE anyone compares them with the CX labels (D23).
Usage: PYTHONPATH=src uv run python evals/scripts/run_cal1_grader.py
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from unbias.evals.claude_cli import ClaudeCliClient
from unbias.evals.grader import GRADER_SYSTEM, Claim, build_grader_prompt, finalize
from unbias.evals.runner import BudgetExhausted

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / "evals/calibration"
plan = json.loads((CAL / "cal1_plan.json").read_text())
packet_path = CAL / "cal1_packet.jsonl"
assert hashlib.sha256(packet_path.read_bytes()).hexdigest() == plan["packet_sha256"], "packet drift"
GRADER = "claude-sonnet-5-5"
client = ClaudeCliClient(
    run_budget_usd=plan["budget_usd"], per_call_cap_usd=plan["per_call_cap_usd"]
)

out = []
for i, line in enumerate(packet_path.read_text().splitlines()):
    item = json.loads(line)
    claims = [Claim(f"c{j}", c["claim"], c["label"]) for j, c in enumerate(item["claims"])]
    prompt, order = build_grader_prompt(
        item["task"], claims, item["reply"], seed=plan["selection_seed"] + i
    )
    payload = {
        "system": GRADER_SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
        "settings": {"model": GRADER},
    }
    try:
        reply = client.complete(payload)
        raw, meta = reply.text, reply.meta
    except BudgetExhausted as e:
        raw, meta = None, {"error": str(e)}
    g = finalize(raw, item["reply"], claims, claim_order=order, grader_model=GRADER)
    rec = asdict(g)
    rec["outcome"] = g.outcome.value
    rec["derived"] = g.derived.value if g.derived else None
    out.append({"id": item["id"], "grade": rec, "client_meta": meta})

path = CAL / "cal1_grader_outputs.jsonl"
path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
digest = hashlib.sha256(path.read_bytes()).hexdigest()
print(
    f"items={len(out)} spent_usd={client.spent_usd:.4f} calls={client.calls} frozen_sha256={digest}"
)
