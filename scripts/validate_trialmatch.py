"""Validation harness: score our trial verdicts against TREC 2022 physician relevance judgments.

For each (patient note, trial) pair in benchmark/trialval/goldset.json — where the physician label
is INDEPENDENT of this project — run the real pipeline (review_pair) and compare our verdict to the
label with the selective-prediction metrics in verdict/trialval.py.

    PYTHONPATH=. .venv/bin/python scripts/validate_trialmatch.py            # resumes; --force to restart
    PYTHONPATH=. .venv/bin/python scripts/validate_trialmatch.py --concurrency 6

Resumable: each scored pair is checkpointed to results.json, so a rate-limit blip or Ctrl-C only
costs the pairs in flight. Honest caveats (also printed): small N, single run (the LLM pipeline is
non-deterministic), and the notes are TREC's physician-written case narratives, not live EHR notes.
"""
import argparse
import concurrent.futures
import json
import os
import threading

from verdict.env import load_dotenv

load_dotenv()

from verdict import trialmatch as tm            # noqa: E402  (after load_dotenv so the key is set)
from verdict.trialval import compute_metrics    # noqa: E402

GOLD = "benchmark/trialval/goldset.json"
RESULTS = "benchmark/trialval/results.json"
REPORT = "benchmark/trialval/report.json"
_LOCK = threading.Lock()


def _load_done(force: bool) -> dict:
    if force or not os.path.exists(RESULTS):
        return {}
    return {(r["topic_id"], r["nct_id"]): r for r in json.load(open(RESULTS))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    gold = json.load(open(GOLD))
    done = _load_done(args.force)
    results = list(done.values())

    # Extract each patient's profile once (reused across that topic's trials) — sequential and cheap.
    notes = {g["topic_id"]: g["note"] for g in gold}
    profiles: dict[int, object] = {}
    for tid, note in notes.items():
        try:
            profiles[tid] = tm.extract_profile(note)
        except Exception as e:  # noqa: BLE001
            print(f"  topic {tid}: profile extraction FAILED ({str(e)[:80]}) — its pairs will error")

    todo = [g for g in gold if (g["topic_id"], g["nct_id"]) not in done]
    print(f"{len(done)} cached · {len(todo)} to score · concurrency {args.concurrency}\n")

    def score(g: dict) -> dict:
        base = {"topic_id": g["topic_id"], "nct_id": g["nct_id"], "gold": g["gold"]}
        prof = profiles.get(g["topic_id"])
        if prof is None:
            return {**base, "verdict": None, "error": "no profile"}
        try:
            card = tm.review_pair(g["note"], g["nct_id"], profile=prof)
            return {**base, "verdict": card.verdict, "n_met": card.n_met,
                    "n_disqualifying": card.n_disqualifying, "n_to_verify": card.n_to_verify}
        except Exception as e:  # noqa: BLE001
            return {**base, "verdict": None, "error": str(e)[:200]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for r in ex.map(score, todo):
            with _LOCK:
                results.append(r)
                json.dump(results, open(RESULTS, "w"), indent=2)   # checkpoint every pair
            v = r.get("verdict") or f"ERROR: {r.get('error', '')[:60]}"
            print(f"  topic {r['topic_id']} {r['nct_id']} gold={r['gold']:8s} -> {v}")

    scored = [r for r in results if r.get("verdict")]
    metrics = compute_metrics(scored)
    metrics["n_errors"] = len(results) - len(scored)
    metrics["source"] = "TREC 2022 Clinical Trials track — physician relevance judgments (qrels)"
    metrics["caveats"] = ("small N; single non-deterministic run; TREC notes are physician-written "
                          "case narratives, not live EHR notes")
    json.dump({"metrics": metrics, "records": results}, open(REPORT, "w"), indent=2)

    m = metrics
    pct = lambda x: "n/a" if x is None else f"{x*100:.0f}%"
    print("\n" + "=" * 60)
    print(f"VALIDATION vs TREC 2022 physician judgments  (n={m['n']}, "
          f"{m['n_eligible']} eligible / {m['n_excluded']} excluded, {m['n_errors']} errored)")
    print("-" * 60)
    print(f"  coverage (makes a definitive call)     {pct(m['coverage'])}")
    print(f"  agreement WHEN it commits              {pct(m['agreement_when_definitive'])}")
    print(f"  CONFIDENT-ERROR rate (contradicts MD)  {pct(m['confident_error_rate'])}   <- the safety number")
    print(f"  abstention rate ('Needs verification') {pct(m['abstention_rate'])}")
    print(f"  exclusion catch rate (of excluded)     {pct(m['exclusion_catch_rate'])}")
    print(f"  false-inclusion rate (of excluded)     {pct(m['false_inclusion_rate'])}")
    print(f"  confusion: {m['confusion']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
