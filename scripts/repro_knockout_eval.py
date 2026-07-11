"""Grounded evaluation of the knockout-control reasoning gate against a labelled corpus.

Runs verdict.knockout.assess_knockout_control over a corpus (each case labelled validated / ambiguous
/ not_reported) and reports accuracy + a Wilson 95% CI + a 3x3 confusion matrix. This is what turns
the gate from "a thin per-paste judgment" into a *measured* reasoning gate.

Two corpora ship:
  - benchmark/repro/knockout_corpus.json       (constructed / synthetic held-out cases)   -> knockout_eval.json
  - benchmark/repro/knockout_corpus_real.json  (real cases paraphrased from open-access papers, PMIDs)
                                                                                            -> knockout_eval_real.json

Requires ANTHROPIC_API_KEY (each case is one Claude reasoning call). Run:
  PYTHONPATH=. .venv/bin/python scripts/repro_knockout_eval.py [corpus.json]
"""
import math
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from verdict.env import load_dotenv

load_dotenv()
from verdict import knockout  # noqa: E402

LABELS = ["validated", "ambiguous", "not_reported"]


def wilson(k: int, n: int, z: float = 1.96) -> list:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - m) / d, 3), round((c + m) / d, 3)]


def run_case(case: dict) -> dict:
    f = knockout.assess_knockout_control(case["methods"], case["antibody"])
    return {"id": case["id"], "antibody": case["antibody"], "gold": case["label"],
            "predicted": f.status, "correct": f.status == case["label"], "hard": bool(case.get("hard"))}


def main() -> None:
    corpus_path = sys.argv[1] if len(sys.argv) > 1 else "benchmark/repro/knockout_corpus.json"
    out_path = corpus_path.replace("corpus", "eval")
    cases = json.load(open(corpus_path))["cases"]

    rows = [None] * len(cases)
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(run_case, c): i for i, c in enumerate(cases)}
        for fut in as_completed(futs):
            rows[futs[fut]] = fut.result()

    n = len(rows)
    correct = sum(r["correct"] for r in rows)
    cm = {g: {p: 0 for p in LABELS} for g in LABELS}
    for r in rows:
        cm[r["gold"]][r["predicted"]] += 1
    false_validated = sum(1 for r in rows if r["predicted"] == "validated" and r["gold"] != "validated")
    # PRODUCT-LEVEL binary: the gate maps validated -> PASS and BOTH ambiguous & not_reported ->
    # NEEDS-VERIFICATION, so the ambiguous<->not_reported confusion is INVISIBLE to the user. What the
    # report card actually decides is PASS vs NEEDS-VERIFICATION — the metric that matters for the tool.
    def prod(lbl: str) -> str:
        return "PASS" if lbl == "validated" else "NEEDS-VERIFICATION"
    prod_correct = sum(1 for r in rows if prod(r["predicted"]) == prod(r["gold"]))
    false_pass = sum(1 for r in rows if prod(r["predicted"]) == "PASS" and prod(r["gold"]) != "PASS")
    missed_pass = sum(1 for r in rows if prod(r["gold"]) == "PASS" and prod(r["predicted"]) != "PASS")
    # hard = genuinely debatable cases (e.g. a knockout run but signal not lost); report separately
    hard = [r for r in rows if r["hard"]]
    non_hard = [r for r in rows if not r["hard"]]
    nh_correct = sum(r["correct"] for r in non_hard)

    summary = {
        "corpus": corpus_path, "n": n,
        "accuracy": round(correct / n, 3), "accuracy_ci95": wilson(correct, n), "correct": correct,
        "false_validated": false_validated,
        "product_binary_accuracy": round(prod_correct / n, 3), "product_binary_ci95": wilson(prod_correct, n),
        "product_false_pass": false_pass, "product_missed_pass": missed_pass,
        "n_hard": len(hard), "hard_correct": sum(r["correct"] for r in hard),
        "accuracy_excluding_hard": round(nh_correct / len(non_hard), 3) if non_hard else None,
        "accuracy_excluding_hard_ci95": wilson(nh_correct, len(non_hard)) if non_hard else None,
        "confusion_matrix": cm, "rows": rows,
    }
    json.dump(summary, open(out_path, "w"), indent=1)

    print(f"=== Knockout gate eval — {corpus_path} (n={n}) ===\n")
    print(f"{'id':<6}{'antibody':<40}{'gold':<14}{'pred':<14}{'ok':<4}{'hard'}")
    for r in rows:
        print(f"{r['id']:<6}{r['antibody'][:38]:<40}{r['gold']:<14}{r['predicted']:<14}"
              f"{'y' if r['correct'] else 'N':<4}{'*' if r['hard'] else ''}")
    ci = summary["accuracy_ci95"]
    print(f"\n3-way label accuracy: {correct}/{n} = {correct / n:.0%}  (Wilson 95% CI {ci[0]:.0%}-{ci[1]:.0%})")
    pci = summary["product_binary_ci95"]
    print(f"PRODUCT binary (PASS vs NEEDS-VERIFICATION): {prod_correct}/{n} = {prod_correct / n:.0%} "
          f"(CI {pci[0]:.0%}-{pci[1]:.0%}) · false-PASS: {false_pass} · missed-PASS: {missed_pass}")
    print(f"false-validated (non-validated called validated — the costly error): {false_validated}")
    if hard:
        eh = summary["accuracy_excluding_hard"]
        print(f"excluding {len(hard)} 'hard' (debatable) cases: {nh_correct}/{len(non_hard)} = {eh:.0%}")
    print("\nconfusion matrix (gold rows x predicted cols):")
    print(f"{'':<14}" + "".join(f"{p:<14}" for p in LABELS))
    for g in LABELS:
        print(f"{g:<14}" + "".join(f"{cm[g][p]:<14}" for p in LABELS))


if __name__ == "__main__":
    main()
