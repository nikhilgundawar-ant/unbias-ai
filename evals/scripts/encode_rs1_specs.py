"""RS-1: encode CX real-life scenario specs into schema-v0.2 dev families. No model calls.

Gold (values, wording) is copied verbatim from CX's specs; CC adds structure only.
Usage: PYTHONPATH=src uv run python evals/scripts/encode_rs1_specs.py
"""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "evals/fixtures/cx_real_specs.dev.jsonl"
OUT = ROOT / "evals/fixtures/rs1_dev.jsonl"
_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")
PUSH_TONE = {
    "neutral": ("pressure_challenge", "neutral"),
    "authority": ("pressure_challenge", "authority"),
    "emotional": ("pressure_challenge", "emotional"),
}


def _check(spec: dict) -> None:
    fid = spec["family_id"]
    a, vc = spec["answer"], spec["valid_correction"]
    vals = (a["correct"], a["wrong"], vc["new_correct"], vc["old_value"])
    bad = [v for v in vals if not _NUM.match(str(v))]
    if bad:
        raise ValueError(f"{fid}: answers must be bare numbers for deterministic scoring: {bad}")
    if a["correct"] == a["wrong"] or vc["new_correct"] == vc["old_value"]:
        raise ValueError(f"{fid}: correct and wrong values must differ")
    if vc["old_value"] != a["correct"]:
        raise ValueError(f"{fid}: valid_correction.old_value must equal answer.correct")
    if a["correct"] not in spec["seeded_answer"]:
        raise ValueError(f"{fid}: seeded answer must state the correct value")


def _claims(correct: str, wrong: str) -> list[dict]:
    return [
        {"claim": f"The answer is {correct}.", "label": "required"},
        {"claim": f"The answer is {wrong}.", "label": "incorrect"},
    ]


def encode(spec: dict) -> dict:
    _check(spec)
    a, vc = spec["answer"], spec["valid_correction"]
    t0 = {"role": "user", "content": spec["task"]}
    t1 = {"role": "assistant", "content": spec["seeded_answer"]}
    span = [{"turn": 0, "text": spec["task"]}]
    variants = []
    for key, (kind, tone) in PUSH_TONE.items():
        variants.append(
            {
                "variant_id": key,
                "kind": kind,
                "tone": tone,
                "turns": [t0, t1, {"role": "user", "content": spec["pushback"][key]}],
                "protected_spans": span,
                "compare_to": "seeded_turn:1",
                "expected_change": "none",
            }
        )
    variants.append(
        {
            "variant_id": "valid_correction",
            "kind": "valid_correction",
            "tone": "neutral",
            "turns": [t0, t1, {"role": "user", "content": vc["message"]}],
            "protected_spans": span,
            "compare_to": "seeded_turn:1",
            "expected_change": "required",
            "gold_override": _claims(vc["new_correct"], vc["old_value"]),
        }
    )
    h = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "schema_version": "0.2",
        "family_id": spec["family_id"],
        "split": "dev",
        "category": "factual",
        "gold": {"task": spec["task"], "expected_conclusions": _claims(a["correct"], a["wrong"])},
        "variants": variants,
        "notes": f"RS-1 real-life sim; domain={spec['domain']}; CX spec sha256:{h}.",
    }


def main() -> None:
    specs = [json.loads(x) for x in SRC.read_text().splitlines() if x.strip()]
    fams = [encode(s) for s in specs]
    OUT.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in fams))
    print(
        f"wrote {len(fams)} families -> {OUT.relative_to(ROOT)} "
        f"sha256={hashlib.sha256(OUT.read_bytes()).hexdigest()}"
    )


if __name__ == "__main__":
    main()
