"""Grounded evaluation of the knockout-control reasoning gate against a labelled corpus.

Runs verdict.knockout.assess_knockout_control over benchmark/repro/knockout_corpus.json (each case
labelled validated / ambiguous / not_reported) and reports accuracy + a 3x3 confusion matrix. This is
what turns the gate from "a thin per-paste judgment" into a *measured* reasoning gate.

Requires ANTHROPIC_API_KEY (each case is one Claude reasoning call). Run:
  PYTHONPATH=. .venv/bin/python scripts/repro_knockout_eval.py
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from verdict.env import load_dotenv

load_dotenv()
from verdict import knockout  # noqa: E402

LABELS = ["validated", "ambiguous", "not_reported"]


def run_case(case: dict) -> dict:
    f = knockout.assess_knockout_control(case["methods"], case["antibody"])
    return {"id": case["id"], "antibody": case["antibody"], "gold": case["label"],
            "predicted": f.status, "result": f.result, "correct": f.status == case["label"],
            "rationale": case["rationale"]}


def main() -> None:
    corpus = json.load(open("benchmark/repro/knockout_corpus.json"))["cases"]
    rows = [None] * len(corpus)
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(run_case, c): i for i, c in enumerate(corpus)}
        for fut in as_completed(futs):
            rows[futs[fut]] = fut.result()

    correct = sum(r["correct"] for r in rows)
    n = len(rows)
    # 3x3 confusion matrix: gold (row) x predicted (col)
    cm = {g: {p: 0 for p in LABELS} for g in LABELS}
    for r in rows:
        cm[r["gold"]][r["predicted"]] += 1
    # a looser "safe" metric: never falsely upgrade a non-validated case to validated (the costly error)
    false_validated = sum(1 for r in rows if r["predicted"] == "validated" and r["gold"] != "validated")

    summary = {
        "n": n, "accuracy": round(correct / n, 3), "correct": correct,
        "false_validated": false_validated,  # non-validated cases the gate wrongly called validated
        "confusion_matrix": cm, "rows": rows,
    }
    json.dump(summary, open("benchmark/repro/knockout_eval.json", "w"), indent=1)

    print(f"=== Knockout-control reasoning gate — grounded eval (n={n}) ===\n")
    print(f"{'id':<7}{'antibody':<16}{'gold':<14}{'predicted':<14}{'ok'}")
    for r in rows:
        print(f"{r['id']:<7}{r['antibody'][:15]:<16}{r['gold']:<14}{r['predicted']:<14}{'y' if r['correct'] else 'N'}")
    print(f"\naccuracy: {correct}/{n} = {correct / n:.0%}")
    print(f"false-validated (non-validated called validated — the costly error): {false_validated}")
    print("\nconfusion matrix (gold rows x predicted cols):")
    print(f"{'':<14}" + "".join(f"{p:<14}" for p in LABELS))
    for g in LABELS:
        print(f"{g:<14}" + "".join(f"{cm[g][p]:<14}" for p in LABELS))


if __name__ == "__main__":
    main()
