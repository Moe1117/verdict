"""(Re)generate the plain-LLM baseline for every benchmark corpus with a REAL, logged Claude call.

The scorecard's plain-LLM comparison must be a LIVE model answer — reproducible by re-running this
script — not a cached string an author can tune. This asks Claude each raw claim directly (no tools,
no evidence, no gates) via verdict.baseline.plain_llm_baseline (the SAME foil the web Duel uses),
writes the answer/confidence/text back into each corpus's `baseline` block, and logs an auditable
record (model id + every raw answer) to benchmark/baselines_audit.json. So the headline becomes
"naive Claude vs Claude + our decidable-gates architecture" — a fair, reproducible, tool-vs-tool
comparison.

Usage: PYTHONPATH=. python scripts/live_baseline.py
"""
from __future__ import annotations

import glob
import json
import os

from verdict.baseline import plain_llm_baseline
from verdict.env import load_dotenv
from verdict.parse import model

CORPORA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "benchmark", "corpora")


def main() -> None:
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("live_baseline needs ANTHROPIC_API_KEY (Claude answers each claim directly).")
        raise SystemExit(2)
    audit = []
    for f in sorted(glob.glob(os.path.join(CORPORA, "*.json"))):
        d = json.load(open(f))
        claim, gold = d["claim"], d.get("expected_verdict")
        b = plain_llm_baseline(claim)
        if not b:
            print(f"  {d['claim_id']}: FAILED (no baseline)")
            continue
        d["baseline"] = b
        with open(f, "w") as fh:
            json.dump(d, fh, indent=2)
            fh.write("\n")
        pred = "Supported" if b["answer"] == "Yes" else "Not Supported"
        # A confident false-positive: a confident (not-low) "Supported" where gold is not Supported.
        conf_fp = b["confidence"] in ("high", "medium") and pred == "Supported" \
            and gold in ("Not Supported", "Insufficient", "Contested")
        audit.append({"id": d["claim_id"], "claim": claim, "gold": gold, "answer": b["answer"],
                      "confidence": b["confidence"], "pred": pred, "confident_false_positive": conf_fp,
                      "text": b["text"]})
        print(f"  {d['claim_id']}: {b['answer']:3} ({b['confidence']:6}) vs gold {gold:14}"
              f"{'   <-- confident FP' if conf_fp else ''}")
    out = os.path.join(os.path.dirname(CORPORA), "baselines_audit.json")
    with open(out, "w") as fh:
        json.dump({"model": model(), "n": len(audit), "baselines": audit}, fh, indent=2)
    cw = sum(1 for a in audit if a["confident_false_positive"])
    print(f"\nnaive Claude ({model()}): {len(audit)} claims, {cw} confident false-positives")
    print(f"audit -> {out}")


if __name__ == "__main__":
    main()
