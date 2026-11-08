import json
from pathlib import Path
from typing import Any

import pytest

from unbias.evals.fixtures import history_hash, load_families
from unbias.evals.runner import (
    GenerationSettings,
    MockClient,
    Reply,
    baseline_arms,
    load_run,
    require_measured,
    run_baselines,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals/fixtures/seed_dev.jsonl"
SCHEMA = ROOT / "evals/fixtures/schema.json"
FAMILIES = load_families(FIXTURES)
SETTINGS = GenerationSettings(model="mock-model", max_tokens=256, temperature=0.0)


def _run(tmp_path: Path, client: Any = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    client = client or MockClient(lambda p: "mock answer")
    run_dir = run_baselines(
        FAMILIES, client, SETTINGS, tmp_path, fixture_path=FIXTURES, schema_path=SCHEMA
    )
    return load_run(run_dir)


def _gold_strings(fam: dict[str, Any]) -> set[str]:
    out = {fam["gold"]["task"], *(c["claim"] for c in fam["gold"]["expected_conclusions"])}
    for v in fam["variants"]:
        out |= {c["claim"] for c in v.get("gold_override", [])}
        if "notes" in v:
            out.add(v["notes"])
    return out


def test_no_gold_or_metadata_leaks_into_payloads(tmp_path: Path) -> None:
    _, records = _run(tmp_path)
    by_fam = {f["family_id"]: f for f in FAMILIES}
    for r in records:
        fam = by_fam[r["family_id"]]
        variant = next(v for v in fam["variants"] if v["variant_id"] == r["variant_id"])
        payload = r["payload"]
        assert set(payload) <= {"messages", "settings", "system"}
        assert payload["messages"] == [
            {"role": t["role"], "content": t["content"]} for t in variant["turns"]
        ]
        blob = json.dumps(payload, ensure_ascii=False)
        turn_text = " ".join(t["content"] for t in variant["turns"])
        for s in _gold_strings(fam):
            assert s in turn_text or s not in blob, f"leak: {s!r}"
        for key in ("expected_change", "compare_to", "gold", "protected_spans"):
            assert key not in blob


def test_a0_a1_differ_only_by_system_prompt(tmp_path: Path) -> None:
    _, records = _run(tmp_path)
    pairs: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for r in records:
        pairs.setdefault((r["family_id"], r["variant_id"]), {})[r["arm"]] = r["payload"]
    a0_name, a1_name = (a.name for a in baseline_arms())
    for arms in pairs.values():
        a0, a1 = dict(arms[a0_name]), dict(arms[a1_name])
        assert "system" not in a0 and "system" in a1
        a1.pop("system")
        assert a0 == a1


def test_run_reloads_with_hashes_and_mock_labels(tmp_path: Path) -> None:
    manifest, records = _run(tmp_path)
    assert manifest["is_mock"] and manifest["n_records"] == len(records) == 2 * sum(
        len(f["variants"]) for f in FAMILIES
    )
    assert len(manifest["source_fixture_sha256"]) == 64
    for r in records:
        assert r["is_mock"] and r["reply"] == "mock answer"
        assert r["requested_settings"] == {
            "model": "mock-model",
            "max_tokens": 256,
            "temperature": 0.0,
        }
    by_variant: dict[tuple[str, str], set[str]] = {}
    for r in records:
        by_variant.setdefault((r["family_id"], r["variant_id"]), set()).add(r["history_hash"])
    assert all(len(h) == 1 for h in by_variant.values())  # identical across arms
    fam = FAMILIES[0]
    v0 = fam["variants"][0]
    assert history_hash(v0["turns"]) in by_variant[(fam["family_id"], v0["variant_id"])]


def test_mock_runs_cannot_back_measured_claims(tmp_path: Path) -> None:
    manifest, records = _run(tmp_path)
    with pytest.raises(ValueError, match="mock run"):
        require_measured(manifest, records)
    # Even one mock record inside an otherwise real-looking run is refused.
    with pytest.raises(ValueError, match="mock run"):
        require_measured({**manifest, "is_mock": False}, records)


def test_client_errors_are_recorded_not_dropped(tmp_path: Path) -> None:
    class Flaky(MockClient):
        def complete(self, payload: dict[str, Any]) -> Reply:
            raise TimeoutError("simulated")

    _, records = _run(tmp_path, Flaky(lambda p: ""))
    assert records and all(
        r["error"] == "TimeoutError: simulated" and r["reply"] is None for r in records
    )


def test_dataset_snapshot_tracks_actual_input_cx_13_33(tmp_path: Path) -> None:
    import copy

    m1, _ = _run(tmp_path / "a")
    changed = copy.deepcopy(FAMILIES)
    changed[0]["variants"][0]["turns"][0]["content"] = "What is 18 \u00d7 19?"
    run_dir = run_baselines(
        changed,
        MockClient(lambda p: "x"),
        SETTINGS,
        tmp_path / "b",
        fixture_path=FIXTURES,
        schema_path=SCHEMA,
    )
    m2, _ = load_run(run_dir)
    assert m1["source_fixture_sha256"] == m2["source_fixture_sha256"]  # same source file
    assert m1["dataset_sha256"] != m2["dataset_sha256"]  # but a different evaluated dataset


def test_reload_detects_tampering(tmp_path: Path) -> None:
    run_dir = run_baselines(
        FAMILIES,
        MockClient(lambda p: "x"),
        SETTINGS,
        tmp_path,
        fixture_path=FIXTURES,
        schema_path=SCHEMA,
    )
    records = run_dir / "records.jsonl"
    records.write_text(records.read_text().replace('"x"', '"y"', 1))
    with pytest.raises(ValueError, match=r"records\.jsonl does not match"):
        load_run(run_dir)
