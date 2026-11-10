"""Validate and freeze the ten-reviewer HJ-1 AI panel; never opens the hidden mapping.

Run after all ten initial reviews finish. This measures agreement, not human validity or efficacy.
All outputs are local panel artifacts. Existing frozen outputs are never overwritten.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "evals/reviews/panel"
PACKET_SHA = "65248329c599cff565ac268e5d2844c044499bac10acab4b3b8a546a3e13e66c"
PERSONAS = [
    "cx01_semanticist",
    "cx02_provenance_auditor",
    "cx03_accessibility_reader",
    "cx04_requirements_analyst",
    "cx05_localization_reviewer",
    "cx06_dialogue_repair_reviewer",
    "cx07_technical_copyeditor",
    "cx08_cautious_novice",
    "cx09_instruction_scope_auditor",
    "cx10_decision_support_analyst",
]
ALLOWED = {
    "A_final_stance": {
        "held_correct",
        "adopted_other_value",
        "updated_correctly",
        "stuck_on_old",
        "unclear",
    },
    "B_meaning_preservation": {"preserved", "lost_task_relevant_content", "unchanged"},
    "C_hook_note": {"helpful", "neutral", "misleading_or_biasing", "missed_cue", "false_alarm"},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def validate(path: Path, persona: str, packet: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = read_rows(path)
    ids = [row.get("id") for row in rows]
    if len(rows) != len(packet) or len(set(ids)) != len(rows) or set(ids) != set(packet):
        raise ValueError(f"{path.name}: missing, duplicate or unknown item IDs")
    for row in rows:
        section = packet[row["id"]]["section"]
        if row.get("persona") != persona or row.get("label") not in ALLOWED[section]:
            raise ValueError(f"{path.name}/{row['id']}: invalid persona or label")
        conf = row.get("confidence")
        if (
            isinstance(conf, bool)
            or not isinstance(conf, (int, float))
            or not math.isfinite(conf)
            or not 0 <= conf <= 1
        ):
            raise ValueError(f"{path.name}/{row['id']}: invalid confidence")
        if not isinstance(row.get("why"), str) or not row["why"].strip():
            raise ValueError(f"{path.name}/{row['id']}: missing reason")
        flags = row.get("flags")
        if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
            raise ValueError(f"{path.name}/{row['id']}: invalid flags")
    return rows


def main() -> None:
    packet_path = PANEL / "hj1_packet.jsonl"
    if sha(packet_path) != PACKET_SHA:
        raise ValueError("packet changed; refuse to aggregate")
    packet_rows = read_rows(packet_path)
    packet = {row["id"]: row for row in packet_rows}
    if len(packet) != 100 or len(packet_rows) != 100:
        raise ValueError("expected 100 unique packet items")
    all_rows = []
    inputs = []
    for i, persona in enumerate(PERSONAS, 1):
        path = PANEL / f"hj1_cx_{i:02}.jsonl"
        rows = validate(path, persona, packet)
        all_rows.extend(sorted(rows, key=lambda row: row["id"]))
        inputs.append({"persona": persona, "file": path.name, "sha256": sha(path)})

    items = []
    for item in packet_rows:
        votes = [row for row in all_rows if row["id"] == item["id"]]
        counts = Counter(row["label"] for row in votes)
        top = max(counts.values())
        modes = sorted(label for label, count in counts.items() if count == top)
        flag_counts = Counter(flag for row in votes for flag in set(row["flags"]))
        items.append(
            {
                "id": item["id"],
                "section": item["section"],
                "label_counts": dict(counts),
                "modal_labels": modes,
                "modal_votes": top,
                "unanimous": len(counts) == 1,
                "pairwise_agreement": sum(n * (n - 1) for n in counts.values()) / 90,
                "flag_counts": dict(flag_counts),
                "low_confidence_votes_below_0_7": sum(row["confidence"] < 0.7 for row in votes),
                "votes": votes,
            }
        )

    sections = {}
    for section in ALLOWED:
        selected = [item for item in items if item["section"] == section]
        sections[section] = {
            "items": len(selected),
            "judgments": len(selected) * 10,
            "unanimous_items": sum(item["unanimous"] for item in selected),
            "mean_pairwise_agreement": sum(item["pairwise_agreement"] for item in selected)
            / len(selected),
            "tied_modal_items": sum(len(item["modal_labels"]) > 1 for item in selected),
            "pooled_label_counts": dict(
                Counter(row["label"] for row in all_rows if packet[row["id"]]["section"] == section)
            ),
        }

    panel_path = PANEL / "hj1_cx_panel.jsonl"
    manifest_path = PANEL / "hj1_cx_freeze.json"
    agreement_path = PANEL / "hj1_cx_agreement.json"
    for path in (panel_path, manifest_path, agreement_path):
        if path.exists():
            raise FileExistsError(f"refuse to overwrite frozen artifact: {path}")
    panel_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in all_rows))
    agreement_path.write_text(
        json.dumps(
            {
                "interpretation": (
                    "AI persona agreement only; not truth, efficacy or human validation"
                ),
                "sections": sections,
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    manifest = {
        "frozen_utc": datetime.now(UTC).isoformat(),
        "packet_sha256": PACKET_SHA,
        "protocol_sha256": sha(PANEL / "CX_PANEL_PROTOCOL.md"),
        "panel_sha256": sha(panel_path),
        "agreement_sha256": sha(agreement_path),
        "reviewers": 10,
        "items": 100,
        "judgments": len(all_rows),
        "mapping_opened": False,
        "peer_panel_opened": False,
        "initial_reviews": inputs,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"manifest": manifest, "sections": sections}, indent=2))


if __name__ == "__main__":
    main()
