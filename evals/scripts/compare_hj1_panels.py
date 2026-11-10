"""Compare frozen AI panels, without reading hidden source/gold mapping.

Requires explicit confirmation that the peer panel is frozen. Reports every disagreement;
neither majority nor cross-panel agreement is treated as validated truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def group(data: list[dict[str, Any]], ids: set[str]) -> tuple[dict[str, list[dict[str, Any]]], int]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_persona: dict[str, set[str]] = defaultdict(set)
    for row in data:
        persona, item = row["persona"], row["id"]
        if item not in ids or item in by_persona[persona]:
            raise ValueError(f"unknown/duplicate item: {persona}/{item}")
        by_persona[persona].add(item)
        by_id[item].append(row)
    if set(by_id) != ids or any(items != ids for items in by_persona.values()):
        raise ValueError("incomplete reviewer panel")
    return by_id, len(by_persona)


def modes(counts: Counter[str]) -> list[str]:
    top = max(counts.values())
    return sorted(label for label, n in counts.items() if n == top)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer-frozen", action="store_true", required=True)
    parser.add_argument("--peer-sha256", required=True)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parents[1] / "reviews/panel"
    freeze = json.loads((folder / "hj1_cx_freeze.json").read_text())
    ours, peer, packet = (
        folder / "hj1_cx_panel.jsonl",
        folder / "hj1_cc_panel.jsonl",
        folder / "hj1_packet.jsonl",
    )
    if sha(ours) != freeze["panel_sha256"] or sha(packet) != freeze["packet_sha256"]:
        raise ValueError("our frozen panel or packet changed")
    if sha(peer) != args.peer_sha256:
        raise ValueError("peer panel differs from declared frozen hash")
    packet_rows = rows(packet)
    ids = {row["id"] for row in packet_rows}
    cx, nx = group(rows(ours), ids)
    cc, nc = group(rows(peer), ids)
    result = []
    for item in packet_rows:
        ident = item["id"]
        x, c = (
            Counter(row["label"] for row in cx[ident]),
            Counter(row["label"] for row in cc[ident]),
        )
        mx, mc = modes(x), modes(c)
        both_unique = len(mx) == len(mc) == 1
        result.append(
            {
                "id": ident,
                "section": item["section"],
                "cx_counts": dict(x),
                "cc_counts": dict(c),
                "cx_modes": mx,
                "cc_modes": mc,
                "unique_modal_agreement": mx == mc if both_unique else None,
                "all_cross_persona_pairs_agreement": sum(n * c[label] for label, n in x.items())
                / (nx * nc),
                "any_label_disagreement": len(set(x) | set(c)) > 1,
            }
        )
    summary = {}
    for section in sorted({item["section"] for item in result}):
        selected = [item for item in result if item["section"] == section]
        summary[section] = {
            "items": len(selected),
            "unique_modal_agreements": sum(
                item["unique_modal_agreement"] is True for item in selected
            ),
            "unique_modal_disagreements": sum(
                item["unique_modal_agreement"] is False for item in selected
            ),
            "ties_not_silently_resolved": sum(
                item["unique_modal_agreement"] is None for item in selected
            ),
            "items_with_any_vote_disagreement": sum(
                item["any_label_disagreement"] for item in selected
            ),
            "mean_all_cross_persona_pairs_agreement": sum(
                item["all_cross_persona_pairs_agreement"] for item in selected
            )
            / len(selected),
        }
    output = {
        "cx_sha256": sha(ours),
        "cc_sha256": sha(peer),
        "cx_personas": nx,
        "cc_personas": nc,
        "interpretation": "Agreement between AI persona panels, not correctness or human validity",
        "hidden_mapping_read": False,
        "summary": summary,
        "items": result,
    }
    path = folder / "hj1_cross_panel.json"
    with path.open("x") as handle:
        handle.write(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"path": str(path), "sha256": sha(path), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
