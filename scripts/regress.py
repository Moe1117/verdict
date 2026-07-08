"""Full regression harness: resolve every labeled claim and score the engine.

Oracle = the 9 frozen corpora (expected_verdict) + the mixed cold set
(/tmp/merged_eval.json, gold.verdict). Prints accuracy, a confusion matrix, the
confidently-wrong count, and every disagreement — so an engine change can be
diffed before/after against ground truth. Deterministic; no network, no LLM.

Usage: PYTHONPATH=. python scripts/regress.py [merged_eval.json]
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys

from verdict.corpora import available, load_rows
from verdict.gates import EvidenceRow, Verdict, resolve

_FIELDS = {f.name for f in dataclasses.fields(EvidenceRow)}
STATES = ["Supported", "Not Supported", "Contested", "Insufficient"]


def _rows(raw: list[dict]) -> list[EvidenceRow]:
    out = []
    for r in raw or []:
        d = {k: v for k, v in r.items() if k in _FIELDS}
        d.setdefault("citation", d.get("source_id", ""))
        out.append(EvidenceRow(**d))
    return out


def _cases(eval_path: str) -> list[dict]:
    cases = []
    # corpora
    for cid in available():
        meta, rows = load_rows(cid)
        cases.append({"id": cid, "src": "corpus", "claim": meta["claim"],
                      "gold": meta["expected_verdict"], "rows": rows})
    # mixed cold set
    if os.path.exists(eval_path):
        data = json.load(open(eval_path))
        if "result" in data:
            data = data["result"] if isinstance(data["result"], dict) else json.loads(data["result"])
        for it in data.get("dataset", []):
            if not it.get("rows") or not it.get("gold"):
                continue
            cases.append({"id": it["id"], "src": "eval", "claim": it["claim"],
                          "gold": it["gold"]["verdict"], "rows": _rows(it["rows"])})
    return cases


def main(eval_path: str = "/tmp/merged_eval.json") -> None:
    cases = _cases(eval_path)
    conf = {g: {p: 0 for p in STATES} for g in STATES}
    errors, conf_wrong = [], 0
    ok = 0
    for c in cases:
        v = resolve(c["rows"])[0].value
        c["pred"] = v
        if c["gold"] in STATES and v in STATES:
            conf[c["gold"]][v] += 1
        if v == c["gold"]:
            ok += 1
        else:
            errors.append(c)
        if c["gold"] in ("Not Supported", "Insufficient") and v == "Supported":
            conf_wrong += 1

    n = len(cases)
    print(f"=== regression: {n} labeled claims (9 corpora + mixed cold set) ===")
    print(f"accuracy: {ok}/{n} = {ok/n:.1%}   confidently-wrong: {conf_wrong}\n")
    print("confusion (rows=gold, cols=pred):")
    print(f"  {'gold\\pred':<16}" + "".join(f"{s[:7]:>9}" for s in STATES))
    for g in STATES:
        print(f"  {g:<16}" + "".join(f"{conf[g][p]:>9}" for p in STATES))
    print(f"\n{len(errors)} disagreements:")
    for c in sorted(errors, key=lambda x: x["src"]):
        print(f"  [{c['src']:6}] {c['id']:5} pred {c['pred']:14} gold {c['gold']:14} | {c['claim'][:50]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/merged_eval.json")
