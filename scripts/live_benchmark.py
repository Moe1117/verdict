"""End-to-end LIVE benchmark — measures the WHOLE system, Claude extraction included.

The curated benchmark (scripts/eval.py) scores the gate engine over hand-authored evidence
rows. This scores the tool a user actually touches: for each claim it runs the live pipeline
from the RAW CLAIM TEXT — Claude parses the claim, PubMed is queried, Claude extracts each
retrieved study into a structured row, the deterministic retraction override + gates decide —
and compares the result to the same gold label. So it captures retrieval recall and extraction
error, which the curated numbers cannot.

Requires ANTHROPIC_API_KEY (+ NCBI_EMAIL per NCBI policy). Results cache per-claim (resumable).

Usage: PYTHONPATH=. python scripts/live_benchmark.py [--k 8] [--ids C08,M07] [--out web/public/live_eval.json]
"""
from __future__ import annotations

import json
import os
import sys
import time

from verdict.corpora import available, load_rows
from verdict.env import load_dotenv
from verdict.verdict import run_live

RETIRED = {"C09", "F02"}


def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _gold_and_claim(cid: str) -> tuple[str, str]:
    meta, _ = load_rows(cid)
    return meta["claim"], meta["expected_verdict"]


def score(results: dict) -> dict:
    scored = [r for r in results.values() if "live_verdict" in r]
    n = len(scored)
    if not n:
        return {"n": 0}
    acc = sum(1 for r in scored if r["correct"]) / n
    decided = [r for r in scored if r["live_verdict"] != "Insufficient"]
    dec_acc = sum(1 for r in decided if r["correct"]) / len(decided) if decided else 0.0
    abstain = sum(1 for r in scored if r["live_verdict"] == "Insufficient") / n
    errs = sum(1 for r in results.values() if "error" in r)
    # A confident FALSE POSITIVE: a decisive 'Supported' the evidence does not warrant — gold is
    # Not Supported, Insufficient, OR genuinely Contested (a firm 'yes' on contested evidence is a
    # false green light too). This is the honest safety metric. The narrow legacy count (gold in
    # {Not Supported, Insufficient} only) is kept alongside for transparency, but the headline is
    # the broad one — asserting Supported on a Contested claim IS a confident error.
    false_pos = sum(1 for r in scored if r["live_verdict"] == "Supported"
                    and r["gold"] in ("Not Supported", "Insufficient", "Contested"))
    false_pos_strict = sum(1 for r in scored if r["live_verdict"] == "Supported"
                           and r["gold"] in ("Not Supported", "Insufficient"))
    return {
        "n": n, "errors": errs,
        "accuracy": round(acc, 3),
        "accuracy_when_answered": round(dec_acc, 3),
        "abstention_rate": round(abstain, 3),
        "confident_false_positives": false_pos,
        "confident_false_positives_strict": false_pos_strict,
        "avg_studies_retrieved": round(sum(r.get("n_ledger", 0) for r in scored) / n, 1),
    }


def main() -> None:
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("live benchmark needs ANTHROPIC_API_KEY (Claude parses + extracts each study).")
        raise SystemExit(2)
    k = int(_arg("--k", "8"))
    out = _arg("--out", "web/public/live_eval.json")
    ids_arg = _arg("--ids", "")
    ids = ids_arg.split(",") if ids_arg else [c for c in available() if c not in RETIRED]

    blob = json.load(open(out)) if os.path.exists(out) else {"results": {}}
    results = blob.get("results", {})
    print(f"live benchmark: {len(ids)} claims, k={k}, out={out}\n")
    for cid in ids:
        if cid in results and "live_verdict" in results[cid]:
            continue  # resume
        claim, gold = _gold_and_claim(cid)
        t0 = time.time()
        try:
            card = run_live(claim, k=k)
            results[cid] = {
                "claim": claim, "gold": gold,
                "live_verdict": card.verdict.value,
                "n_ledger": len(card.ledger),
                "n_excluded": sum(1 for r in card.ledger if not r.integrity_ok),
                "correct": card.verdict.value == gold,
            }
        except Exception as e:  # noqa: BLE001 — one bad claim never sinks the run
            results[cid] = {"claim": claim, "gold": gold, "error": f"{type(e).__name__}: {e}"[:200]}
        blob["results"] = results
        blob["summary"] = score(results)
        with open(out, "w") as fh:
            json.dump(blob, fh, indent=2)
        r = results[cid]
        tag = r.get("live_verdict", "ERROR")
        mark = "  ok" if r.get("correct") else ("" if "live_verdict" in r else "  [err]")
        print(f"  {cid}: {tag:14} gold {gold:14} ({r.get('n_ledger', 0)} studies, {time.time()-t0:.0f}s){mark}")

    s = blob["summary"]
    print(f"\n=== LIVE end-to-end (n={s['n']}, {s.get('errors', 0)} errored) ===")
    print(f"  accuracy vs gold        : {s['accuracy']:.0%}")
    print(f"  accuracy when answered  : {s['accuracy_when_answered']:.0%}")
    print(f"  abstention rate         : {s['abstention_rate']:.0%}")
    print(f"  confident false-positives: {s['confident_false_positives']} "
          f"(strict, gold no/unknown only: {s['confident_false_positives_strict']})")
    print(f"  avg studies retrieved   : {s['avg_studies_retrieved']}")
    print("\n(curated gate-engine benchmark for comparison: 91% accuracy, 0 confidently-wrong)")


if __name__ == "__main__":
    main()
