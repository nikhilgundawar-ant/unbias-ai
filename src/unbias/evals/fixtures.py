"""Load and check seed-family fixtures (schema v0.2, decision D9).

All schema knowledge lives here and in `evals/fixtures/schema.json`, so schema changes
do not touch metric code.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

Family = dict[str, Any]

# D9: which change references each variant kind may use.
_ALLOWED_REF = {
    "base": {"none"},
    "tone_only": {"variant"},
    "false_premise": {"variant"},
    "language_change": {"variant"},
    "evidence_change": {"variant"},
    "preference_change": {"variant"},
    "pressure_challenge": {"seeded_turn"},
    "valid_correction": {"seeded_turn"},
}


def history_hash(turns: Sequence[Mapping[str, str]]) -> str:
    """Canonical hash of a seeded INPUT history (role + content only), G1-R3.

    Identical across arms for the same probe. Constructed answering payloads legitimately differ
    by arm and are hashed separately in the replay manifest.
    """
    canon = [{"role": t["role"], "content": t["content"]} for t in turns]
    blob = json.dumps(canon, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class FixtureError(ValueError):
    """A fixture file is malformed or violates a protocol rule."""


def load_families(path: Path) -> list[Family]:
    families: list[Family] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            families.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise FixtureError(f"{path}:{lineno}: invalid JSON: {e}") from e
    return families


def check_families(families: list[Family], schema_path: Path) -> None:
    """JSON Schema validation plus the semantic rules the schema cannot express."""
    import jsonschema  # optional dependency: `unbias-ai[evals]`

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for fam in families:
        fid = fam.get("family_id", "<missing>")
        try:
            jsonschema.validate(fam, schema)
        except jsonschema.ValidationError as e:
            raise FixtureError(f"{fid}: {e.message}") from e
        if fid in seen:
            raise FixtureError(f"{fid}: duplicate family_id")
        seen.add(fid)
        _check_family(fam)


def _check_family(fam: Family) -> None:
    fid = fam["family_id"]
    variants = {v["variant_id"]: v for v in fam["variants"]}
    if len(variants) != len(fam["variants"]):
        raise FixtureError(f"{fid}: duplicate variant_id")

    refs: dict[str, str] = {}
    for vid, v in variants.items():
        where = f"{fid}/{vid}"
        turns = v["turns"]
        if turns[-1]["role"] != "user":
            raise FixtureError(f"{where}: last turn must be from the user")
        for span in v.get("protected_spans", []):
            i = span["turn"]
            if i >= len(turns) or span["text"] not in turns[i]["content"]:
                raise FixtureError(f"{where}: protected span not in turn {i}: {span['text']!r}")

        ref_kind, _, ref_arg = v["compare_to"].partition(":")
        if ref_kind not in _ALLOWED_REF[v["kind"]]:
            raise FixtureError(f"{where}: kind {v['kind']!r} cannot use compare_to {ref_kind!r}")
        if ref_kind == "none" and v["expected_change"] != "none":
            raise FixtureError(f"{where}: expected_change must be 'none' when compare_to is none")
        if ref_kind == "seeded_turn":
            idx = int(ref_arg)
            if idx >= len(turns) - 1 or turns[idx]["role"] != "assistant":
                raise FixtureError(f"{where}: seeded_turn:{idx} must be an earlier assistant turn")
        if ref_kind == "variant":
            if ref_arg == vid:
                raise FixtureError(f"{where}: variant references itself")
            if ref_arg not in variants:
                raise FixtureError(f"{where}: unknown reference variant {ref_arg!r}")
            refs[vid] = ref_arg

    for start in refs:  # reference chains must end at a non-variant reference
        node, path = start, {start}
        while node in refs:
            node = refs[node]
            if node in path:
                raise FixtureError(f"{fid}: cyclic compare_to involving {start!r}")
            path.add(node)
