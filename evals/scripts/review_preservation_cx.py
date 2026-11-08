"""Offline independent CX fixture review. Stub plumbing only; never calls a model.

Run with PYTHONPATH=src and --out PATH. Refuses to overwrite an earlier review.
Original gold stays fixed even if the implementation later changes its schema.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from unbias.neutralizer import neutralize

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "evals/fixtures/preservation_cx.dev.jsonl"


def review(mode: str = "apply") -> dict:
    results = []
    for row in map(json.loads, FIXTURE.read_text().splitlines()):
        for role in ("oracle", "unsafe"):
            payload = {
                "task_parts": [{"source_span": row["task_span"]}],
                "relevant_context": [],
                "attributed_assertions": [],
                "preferences_constraints": [],
                "ambiguities": [],
                "set_aside": [
                    {"source_span": s, "reason": "fixed fixture stub"}
                    for s in row[f"{role}_set_aside"]
                ],
                "relevance_confident": True,
            }
            raw = json.dumps(payload)
            result = neutralize(row["input"], lambda _, raw=raw: raw, apply=mode == "apply")
            actual = result.applied_cuts
            protected_overlap = any(
                start < p["end"] and p["start"] < end
                for start, end in actual
                for p in row["protected_spans"]
            )
            outside_allowed = any(
                not any(a["start"] <= start and end <= a["end"] for a in row["allowed_cuts"])
                for start, end in actual
            )
            if mode == "suggest":
                meets_expectation = result.prompt == row["input"] and not actual
            elif role == "oracle":
                meets_expectation = (
                    result.prompt == row["expected_oracle_prompt"] and not result.fallback
                )
            else:
                meets_expectation = result.prompt == row["input"] and result.fallback
            results.append(
                {
                    "id": row["id"],
                    "role": role,
                    "pass_check": meets_expectation
                    and not protected_overlap
                    and not outside_allowed,
                    "prompt": result.prompt,
                    "fallback": result.fallback,
                    "problems": result.problems,
                    "removed": result.removed,
                    "proposed_cut_ranges": result.proposed_cuts,
                    "actual_cut_ranges": actual,
                    "protected_overlap": protected_overlap,
                    "outside_allowed": outside_allowed,
                }
            )
    return {
        "scope": "offline fixed stub verifier only; not live extractor accuracy",
        "mode": mode,
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(
            (ROOT / "src/unbias/neutralizer.py").read_bytes()
        ).hexdigest(),
        "review_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--mode", choices=("apply", "suggest"), default="apply")
    args = parser.parse_args()
    report = review(args.mode)
    with args.out.open("x") as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for role in ("oracle", "unsafe"):
        rows = [r for r in report["results"] if r["role"] == role]
        print(f"{role}: {sum(r['pass_check'] for r in rows)}/{len(rows)} meets fixed expectation")
