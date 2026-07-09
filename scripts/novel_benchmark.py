"""Novel-claim head-to-head: naive Claude vs the full live Verdict product, on claims a training-
cutoff LLM would MISS (recent trial readouts). The curated benchmark is all famous claims, which
favors a memorizing LLM; this tests where the architecture — live retrieval + deterministic gates —
should actually win: naive Claude must guess, Verdict retrieves the real paper and gates it.

Usage: PYTHONPATH=. python scripts/novel_benchmark.py benchmark/novel_claims.json [out.json]
"""
from __future__ import annotations

import json
import os
import sys
import time

from verdict.baseline import plain_llm_baseline
from verdict.certainty import grade_certainty
from verdict.env import load_dotenv
from verdict.verdict import run_live

NOT_POSITIVE = ("Not Supported", "Insufficient", "Contested")


def _confident_fp(pred: str | None, gold: str, confident: bool) -> bool:
    """Broad definition: a CONFIDENT 'Supported' where the truth is not Supported. Symmetric across
    arms — naive Claude is 'confident' at high/medium confidence, Verdict at High/Moderate certainty
    — so neither side gets a free pass."""
    return bool(confident and pred == "Supported" and gold in NOT_POSITIVE)


def main() -> None:
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("novel_benchmark needs ANTHROPIC_API_KEY")
    raw = json.load(open(sys.argv[1]))
    claims = raw.get("claims", raw) if isinstance(raw, dict) else raw
    out = sys.argv[2] if len(sys.argv) > 2 else "web/public/novel_eval.json"
    results = []
    for c in claims:
        claim, gold = c["claim"], c["true_verdict"]
        t0 = time.time()
        b = plain_llm_baseline(claim)
        npred = None if not b else ("Supported" if b["answer"] == "Yes" else "Not Supported")
        nconf = (b or {}).get("confidence", "low")
        vcert = "Very Low"
        try:
            card = run_live(claim, k=8)
            vverdict = card.verdict.value
            vcert = grade_certainty(card.ledger, card.verdict).level
        except Exception as e:  # noqa: BLE001
            vverdict = f"ERROR:{type(e).__name__}"
        r = {
            "claim": claim, "gold": gold,
            "naive_pred": npred, "naive_conf": nconf, "naive_correct": npred == gold,
            "naive_confident_fp": _confident_fp(npred, gold, nconf in ("high", "medium")),
            "verdict": vverdict, "verdict_cert": vcert, "verdict_correct": vverdict == gold,
            "verdict_confident_fp": _confident_fp(vverdict, gold, vcert in ("High", "Moderate")),
            "sec": round(time.time() - t0),
        }
        results.append(r)
        json.dump({"results": results}, open(out, "w"), indent=2)
        print(f"  {claim[:50]:52} gold {gold:14} | naive {str(npred):14}{'ok' if r['naive_correct'] else '  '}"
              f" | verdict {vverdict:14}{'ok' if r['verdict_correct'] else ''}")

    n = len(results) or 1
    summary = {
        "n": len(results),
        "naive_accuracy": round(sum(r["naive_correct"] for r in results) / n, 3),
        "naive_confident_fp": sum(r["naive_confident_fp"] for r in results),
        "verdict_accuracy": round(sum(r["verdict_correct"] for r in results) / n, 3),
        "verdict_confident_fp": sum(r["verdict_confident_fp"] for r in results),
        "verdict_abstention": round(sum(1 for r in results if r["verdict"] in ("Insufficient", "Contested")) / n, 3),
    }
    json.dump({"summary": summary, "results": results}, open(out, "w"), indent=2)
    s = summary
    print(f"\n=== NOVEL claims (n={s['n']}) — naive Claude vs the live Verdict product ===")
    print(f"  naive Claude : accuracy {s['naive_accuracy']:.0%}, confident false-positives {s['naive_confident_fp']}")
    print(f"  Verdict live : accuracy {s['verdict_accuracy']:.0%}, confident false-positives {s['verdict_confident_fp']}, "
          f"abstains {s['verdict_abstention']:.0%}")


if __name__ == "__main__":
    main()
