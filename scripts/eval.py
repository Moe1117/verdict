"""Score a cold-set evaluation dataset with the REAL gate engine.

Usage: python scripts/eval.py <dataset.json>

Input: {"dataset": [{id, claim, rows[], gold{verdict}, baseline{answer,confidence}}]}
(a raw workflow wrapper {"result": ...} is unwrapped).

Compares three methods against the independent expert-consensus gold:
  - Verdict   : the deterministic gate engine over the extracted rows (can abstain).
  - Naive-vote: majority study direction, NO quality/integrity/population weighting
                (the "consensus-meter" approach; cannot abstain).
  - Plain-LLM : a confident Yes/No with no ability to abstain.
Writes web/public/eval.json and prints a report. Reports Verdict's errors too.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys

from verdict.gates import EvidenceRow, resolve

_FIELDS = {f.name for f in dataclasses.fields(EvidenceRow)}
WEB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "public")


def _rows(item) -> list[EvidenceRow]:
    out = []
    for r in (item.get("rows") or []):
        d = {k: v for k, v in r.items() if k in _FIELDS}
        d.setdefault("citation", d.get("source_id", ""))
        out.append(EvidenceRow(**d))
    return out


def _naive_vote(rows: list[EvidenceRow]) -> str:
    """Count studies with NO integrity/quality/population weighting (incl. retracted)."""
    pro = sum(1 for r in rows if r.direction == 1)
    con = sum(1 for r in rows if r.direction in (-1, 0))
    if pro > con:
        return "Supported"
    if con > pro:
        return "Not Supported"
    return "Contested"


def main(path: str, out: str = "eval.json") -> None:
    data = json.load(open(path))
    if "result" in data:
        data = data["result"] if isinstance(data["result"], dict) else json.loads(data["result"])
    scored = []
    for it in data["dataset"]:
        if not it.get("rows") or not it.get("gold") or not it.get("baseline"):
            continue
        rows = _rows(it)
        if not rows:
            continue
        scored.append({
            "id": it["id"], "claim": it["claim"],
            "gold": it["gold"]["verdict"],
            "verdict": resolve(rows)[0].value,
            "naive": _naive_vote(rows),
            "baseline": "Supported" if it["baseline"]["answer"] == "Yes" else "Not Supported",
            "base_conf": it["baseline"].get("confidence", "?"),
        })

    n = len(scored)
    if not n:
        print("no scorable claims")
        return

    def acc(key):
        return sum(1 for r in scored if r[key] == r["gold"]) / n

    decided = [r for r in scored if r["verdict"] != "Insufficient"]
    dec_acc = sum(1 for r in decided if r["verdict"] == r["gold"]) / len(decided) if decided else 0.0
    abstain = sum(1 for r in scored if r["verdict"] == "Insufficient") / n

    # "Confidently wrong": asserted a positive when the honest answer is no / don't-know.
    def conf_wrong(key):
        return sum(1 for r in scored if r["gold"] in ("Not Supported", "Insufficient") and r[key] == "Supported")

    summary = {
        "n": n,
        "accuracy": {"verdict": round(acc("verdict"), 3), "naive_vote": round(acc("naive"), 3), "plain_llm": round(acc("baseline"), 3)},
        "verdict_accuracy_when_answered": round(dec_acc, 3),
        "verdict_abstention_rate": round(abstain, 3),
        "confidently_wrong": {"verdict": conf_wrong("verdict"), "naive_vote": conf_wrong("naive"), "plain_llm": conf_wrong("baseline")},
    }

    os.makedirs(WEB, exist_ok=True)
    with open(os.path.join(WEB, out), "w") as fh:
        json.dump({"summary": summary, "claims": scored}, fh, indent=2)

    print(f"=== Verdict cold-set evaluation (n={n}) ===\n")
    print("Accuracy vs independent expert-consensus gold (exact 4-state match):")
    print(f"  Verdict (gate engine) : {acc('verdict'):.0%}")
    print(f"  Naive study-count vote: {acc('naive'):.0%}")
    print(f"  Plain-LLM (confident) : {acc('baseline'):.0%}\n")
    print(f"Verdict abstains on {abstain:.0%} of claims; when it DOES answer, {dec_acc:.0%} accurate.\n")
    print("Confidently wrong (asserted a positive when the honest answer is no / don't-know):")
    print(f"  Verdict : {conf_wrong('verdict')} / {n}")
    print(f"  Naive   : {conf_wrong('naive')} / {n}")
    print(f"  Plain-LLM: {conf_wrong('baseline')} / {n}\n")
    print("Verdict errors (verdict != gold) — reported honestly:")
    for r in scored:
        if r["verdict"] != r["gold"]:
            print(f"  {r['id']} got {r['verdict']:14} gold {r['gold']:14} | {r['claim'][:52]}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "eval.json")
