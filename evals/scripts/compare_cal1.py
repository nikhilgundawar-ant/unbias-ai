"""CAL-1 step 3: compare FROZEN grader outputs with CX AI reference labels (D23). No calls.
Agreement uses the grader's DERIVED outcome; queued/invalid/failed count as non-agreement.
Usage: uv run python evals/scripts/compare_cal1.py <expected_grader_sha256>
"""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

CAL = Path(__file__).resolve().parents[2] / "evals/calibration"
grader_path = CAL / "cal1_grader_outputs.jsonl"
if hashlib.sha256(grader_path.read_bytes()).hexdigest() != sys.argv[1]:
    sys.exit("grader outputs changed since they were frozen")
grades = {r["id"]: r["grade"] for r in map(json.loads, grader_path.read_text().splitlines())}
labels = {
    r["id"]: r for r in map(json.loads, (CAL / "cal1_cx_labels.jsonl").read_text().splitlines())
}
mapping = json.loads((CAL / "cal1_mapping.DO_NOT_OPEN_BEFORE_LABELLING.json").read_text())
assert set(grades) == set(labels) == set(mapping), "id sets differ"


def grader_outcome(g: dict) -> str:
    return "queued" if g["queued"] else g["outcome"]


real = [i for i, m in mapping.items() if m["kind"] == "real"]
agree = sum(grader_outcome(grades[i]) == labels[i]["outcome"] for i in real)
confusion = Counter((labels[i]["outcome"], grader_outcome(grades[i])) for i in real)
critical = [
    i
    for i, m in mapping.items()
    if m["kind"] == "control"
    and m["expected"] == "incorrect"
    and grader_outcome(grades[i]) == "correct"
]
ctrl_vs_expected = Counter(
    (m["expected"], grader_outcome(grades[i])) for i, m in mapping.items() if m["kind"] == "control"
)
ctrl_cx = sum(
    labels[i]["outcome"] == m["expected"] for i, m in mapping.items() if m["kind"] == "control"
)
n_ctrl = sum(m["kind"] == "control" for m in mapping.values())
rate = agree / len(real)
print(f"real agreement (grader derived vs CX AI reference): {agree}/{len(real)} = {rate:.0%}")
print(f"queued among real: {sum(grades[i]['queued'] for i in real)}")
print("confusion (cx_label, grader):", dict(confusion))
print("controls (expected, grader):", dict(ctrl_vs_expected))
print(f"CX labels matching control expectations: {ctrl_cx}/{n_ctrl}")
print(f"known-incorrect->correct on controls: {len(critical)} {critical}")
passed = rate >= 0.85 and not critical
print("GATE (provisional engineering check, D23):", "PASS" if passed else "FAIL")
