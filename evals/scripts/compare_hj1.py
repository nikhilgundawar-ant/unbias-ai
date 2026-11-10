"""HISTORICAL (superseded): preliminary 9-reviewer HJ-1 comparison. Opened the mapping before the
CX 10-reviewer freeze (protocol deviation, see reports/HJ1_PERSONA_PANELS.md). Use compare_hj1_panels.py.

AI persona panels, NOT human validation. No model calls. Reads the frozen panel files, then the
mapping, and writes `evals/reviews/panel/hj1_comparison.json` plus a markdown table to stdout.
Usage: python3 evals/scripts/compare_hj1.py
"""

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "evals/reviews/panel"
FROZEN = {  # recorded in COMMON_CONTEXT before the mapping was opened
    "hj1_cc_panel.jsonl": "87b6d972774a8110abaeb01c10a3fc38174b3e0df2be64960865937cd1ad7ad3",
    "hj1_cx_01.jsonl": "5f7e4670e875c81ba155c85953a2ca486749662348dd91c0acf01ac0e28c1a31",
    "hj1_cx_02.jsonl": "0488b12a5813f99eab799ffcff45b10d5716e53155890c228268a0db37cc07b6",
    "hj1_cx_03.jsonl": "5e037e2338b76c527b142048d0c69231f8409aaf6d371f5b6571702192823e78",
    "hj1_cx_04.jsonl": "3d36eb3b4c93fa4d719248ea1768285e11e20259728df0a8f21287f595c4bb97",
    "hj1_cx_05.jsonl": "cfc38f871f1d59aabe574efcf1763f651a8c9e1e7397cbf5471d5549d47ab508",
    "hj1_cx_06.jsonl": "ae7ef06ef12b914929b8eafb2e8b699187e84f5e3b54290b2e8a757f8bb0b923",
    "hj1_cx_07.jsonl": "b35c1f943a778695cd962bb8679964186b7cfd9f392a471035ef06a5bf14e73c",
    "hj1_cx_08.jsonl": "8ccc6ed7765c36c0028b15af4318bc3defd823168beb24205f679b39c3ce97a1",
    "hj1_cx_09.jsonl": "36578dc9ce8a75b1efc6909007ac147665f9ec9c3a7dcd3b3a75ae35903b2cfd",
}
SECTIONS = ("A_final_stance", "B_meaning_preservation", "C_hook_note")
OLD_A = {"held": "held_correct", "updated": "updated_correctly"}


def rows(name: str) -> list[dict]:
    data = (P / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != FROZEN[name]:
        raise SystemExit(f"{name} changed after freeze")
    return [json.loads(x) for x in data.decode().splitlines()]


def fleiss(tables: list[Counter]) -> float | None:
    """Fleiss' kappa over items with >=2 raters; unequal rater counts handled per item."""
    items = [t for t in tables if sum(t.values()) >= 2]
    if not items:
        return None
    cats = Counter()
    p_bar = 0.0
    for t in items:
        n = sum(t.values())
        p_bar += (sum(v * v for v in t.values()) - n) / (n * (n - 1))
        for k, v in t.items():
            cats[k] += v / n
    p_bar /= len(items)
    p_e = sum((v / len(items)) ** 2 for v in cats.values())
    return None if p_e == 1 else (p_bar - p_e) / (1 - p_e)


def cohen(a: list[str], b: list[str]) -> float | None:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in ca) / (n * n)
    return None if pe == 1 else (po - pe) / (1 - pe)


def majority(t: Counter) -> str:
    top = t.most_common()
    return (
        "TIE:" + "/".join(sorted(k for k, v in top if v == top[0][1]))
        if len(top) > 1 and top[0][1] == top[1][1]
        else top[0][0]
    )


def main() -> None:
    packet = {json.loads(x)["id"]: json.loads(x) for x in (P / "hj1_packet.jsonl").open()}
    panels: dict[str, dict[str, Counter]] = {"CC": {}, "CX": {}}
    for name in FROZEN:
        side = "CC" if "_cc_" in name else "CX"
        for r in rows(name):
            panels[side].setdefault(r["id"], Counter())[r["label"]] += 1
    for side, d in panels.items():
        assert set(d) == set(packet), f"{side} coverage mismatch"

    mapping = json.loads((P / "hj1_mapping.DO_NOT_OPEN_BEFORE_LABELLING.json").read_text())
    cc_old = {
        json.loads(x)["payload_hash"] + json.loads(x)["run_dir"]: json.loads(x)
        for x in (ROOT / "evals/reviews/rs1_cc_audit.jsonl").open()
    }
    cx_old = {
        json.loads(x)["id"]: json.loads(x)["label"]
        for x in (ROOT / "evals/reviews/rs1_cx_audit.jsonl").open()
    }

    out: dict = {
        "label": "AI persona panels (CC 7 + CX 9); NOT human validation",
        "sections": {},
        "items": [],
    }
    for sec in SECTIONS:
        ids = [i for i in packet if packet[i]["section"] == sec]
        mc = [majority(panels["CC"][i]) for i in ids]
        mx = [majority(panels["CX"][i]) for i in ids]
        pooled = [panels["CC"][i] + panels["CX"][i] for i in ids]
        out["sections"][sec] = {
            "n": len(ids),
            "fleiss_CC": fleiss([panels["CC"][i] for i in ids]),
            "fleiss_CX": fleiss([panels["CX"][i] for i in ids]),
            "fleiss_pooled": fleiss(pooled),
            "majority_agree": sum(a == b for a, b in zip(mc, mx, strict=True)),
            "cohen_majorities": cohen(mc, mx),
            "unanimous_pooled": sum(len(t) == 1 for t in pooled),
            "CC_majorities": dict(Counter(mc)),
            "CX_majorities": dict(Counter(mx)),
        }
        for i, a, b in zip(ids, mc, mx, strict=True):
            m = mapping[i]
            ref = None
            if m["kind"] == "rs1":
                old = cc_old.get(m["payload_hash"] + m["run"])
                ref = {
                    "cc_audit": OLD_A.get(old["cc_label"], old["cc_label"]) if old else None,
                    "cx_audit": OLD_A.get(cx_old.get(old["id"]), cx_old.get(old["id"]))
                    if old
                    else None,
                }
            elif m["kind"] == "preservation":
                ref = {
                    "probe": m["probe"],
                    "fallback": m["fallback"],
                    "design_expectation": "lost_task_relevant_content"
                    if m["probe"] == "unsafe" and not m["fallback"]
                    else "not_lost",
                }
            else:
                from_packet = packet[i]
                ref = {
                    "prompt": from_packet["user_message"],
                    "note_present": from_packet["note_added_for_claude"] != "(no note added)",
                }
            out["items"].append(
                {
                    "id": i,
                    "section": sec,
                    "kind": m["kind"],
                    "CC": dict(panels["CC"][i]),
                    "CX": dict(panels["CX"][i]),
                    "CC_major": a,
                    "CX_major": b,
                    "ref": ref,
                    "map": m,
                }
            )
    (P / "hj1_comparison.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out["sections"], indent=1))


if __name__ == "__main__":
    main()
