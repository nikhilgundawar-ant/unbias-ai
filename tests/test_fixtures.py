import copy
import json
from pathlib import Path
from typing import Any

import pytest

from unbias.evals.fixtures import FixtureError, check_families, load_families

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "evals/fixtures/schema.json"
SEEDS = load_families(ROOT / "evals/fixtures/seed_dev.jsonl")


def _family(fid: str) -> dict[str, Any]:
    return copy.deepcopy(next(f for f in SEEDS if f["family_id"] == fid))


def test_seed_dev_fixtures_are_valid() -> None:
    assert len(SEEDS) >= 11
    check_families(SEEDS, SCHEMA)


@pytest.mark.parametrize(
    ("fid", "mutate", "error"),
    [
        (
            "arith_17x19",
            lambda f: f["variants"][1].update(protected_spans=[{"turn": 0, "text": "nope"}]),
            "protected span",
        ),
        (
            "arith_pushback",
            lambda f: (
                f["variants"][0]["protected_spans"].append({"turn": 1, "text": "No, you idiot"})
                if "protected_spans" in f["variants"][0]
                else f["variants"][0].update(protected_spans=[{"turn": 0, "text": "No, you idiot"}])
            ),
            "protected span",
        ),
        (
            "arith_17x19",
            lambda f: f["variants"][1].update(compare_to="variant:attributed"),
            "references itself",
        ),
        (
            "arith_17x19",
            lambda f: f["variants"][0].update(kind="tone_only", compare_to="variant:authority"),
            "cyclic",
        ),
        (
            "arith_17x19",
            lambda f: f["variants"][1].update(compare_to="variant:missing"),
            "unknown reference",
        ),
        (
            "arith_pushback",
            lambda f: f["variants"][0].update(compare_to="seeded_turn:0"),
            "earlier assistant turn",
        ),
        (
            "arith_pushback",
            lambda f: f["variants"][0].update(compare_to="variant:valid_fix_on_wrong"),
            "cannot use compare_to",
        ),
        (
            "arith_17x19",
            lambda f: f["variants"][0].update(expected_change="required"),
            "must be 'none'",
        ),
        ("arith_17x19", lambda f: f["variants"][0].update(compare_to="gold"), "does not match"),
    ],
)
def test_semantic_violations_are_rejected(fid: str, mutate: Any, error: str) -> None:
    fam = _family(fid)
    mutate(fam)
    with pytest.raises(FixtureError, match=error):
        check_families([fam], SCHEMA)


def test_duplicate_family_rejected() -> None:
    fam = _family("arith_17x19")
    with pytest.raises(FixtureError, match="duplicate family_id"):
        check_families([fam, copy.deepcopy(fam)], SCHEMA)


def test_seed_file_is_valid_jsonl() -> None:
    for line in (ROOT / "evals/fixtures/seed_dev.jsonl").read_text().splitlines():
        json.loads(line)


def test_h2_families_valid_and_match_cx_specs() -> None:
    h2 = load_families(ROOT / "evals/fixtures/h2_dev.jsonl")
    check_families(h2, SCHEMA)
    specs = {
        s["family_id"]: s
        for s in (
            json.loads(x)
            for x in (ROOT / "evals/fixtures/cx_gold_specs.dev.jsonl").read_text().splitlines()
            if x.strip()
        )
    }
    assert {f["family_id"] for f in h2} == set(specs)
    for f in h2:  # gold copied verbatim from CX; CC never edits labels
        s = specs[f["family_id"]]
        got = {(c["claim"], c["label"]) for c in f["gold"]["expected_conclusions"]}
        want = {(c, "required") for c in s["required"]} | {(c, "incorrect") for c in s["incorrect"]}
        want |= {(c, "acceptable") for c in s.get("acceptable", [])}
        assert got == want and f["gold"]["task"] == f"{s['evidence']}\n\n{s['neutral_task']}"
