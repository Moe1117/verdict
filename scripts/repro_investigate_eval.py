"""Measured evaluation of the Agentic Investigator against known-answer cases (live PubMed + Cellosaurus).

For each case runs the REAL agentic loop and scores: class accuracy (did the verdict match the expected
class), false-validation (a negative wrongly returned FOUND_VALIDATION — the costly error, must be 0),
and expected-citation hits (did the grounded citations include the real record we expected). Reports
Wilson 95% CIs. Every citation is deterministically verified against real retrieval, so a cited id is
real by construction — this measures whether the agent finds the right real evidence, not whether it
hallucinates (it structurally cannot).

Requires ANTHROPIC_API_KEY + NCBI_EMAIL. Slow (each case is a full agentic loop). Run:
  PYTHONPATH=. .venv/bin/python scripts/repro_investigate_eval.py
"""
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

from verdict.env import load_dotenv

load_dotenv()
from verdict import investigate  # noqa: E402


def wilson(k: int, n: int, z: float = 1.96) -> list:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - m) / d, 3), round((c + m) / d, 3)]


def run_case(case: dict) -> dict:
    if case["kind"] == "cell_line":
        inv = investigate.investigate_cell_line(case["name"], iclac_id=case.get("iclac_id", ""),
                                                cvcl=case.get("cvcl", ""))
    else:
        inv = investigate.investigate_antibody(case["name"], target=case.get("target", ""))
    cited = [c.id for c in inv.cited]
    exp_id = case.get("expect_id", "")
    return {"id": case["id"], "kind": case["kind"], "name": case["name"], "expect": case["expect"],
            "verdict": inv.verdict, "grounded": inv.grounded, "cited": cited,
            "class_correct": inv.verdict == case["expect"],
            "expected_citation_hit": (exp_id in cited) if exp_id else None,
            "is_negative": case["expect"] == "NO_VALIDATION_FOUND"}


def main() -> None:
    cases = json.load(open("benchmark/repro/investigate_corpus.json"))["cases"]
    rows = [None] * len(cases)
    with ThreadPoolExecutor(max_workers=3) as ex:  # modest: respect NCBI rate + API concurrency
        futs = {ex.submit(run_case, c): i for i, c in enumerate(cases)}
        for fut in as_completed(futs):
            rows[futs[fut]] = fut.result()

    n = len(rows)
    correct = sum(r["class_correct"] for r in rows)
    negatives = [r for r in rows if r["is_negative"]]
    positives = [r for r in rows if not r["is_negative"]]
    false_validation = sum(1 for r in negatives if r["verdict"] == "FOUND_VALIDATION")  # costly error
    pos_found = sum(1 for r in positives if r["class_correct"] and r["grounded"])
    with_exp = [r for r in rows if r["expected_citation_hit"] is not None]
    exp_hit = sum(1 for r in with_exp if r["expected_citation_hit"])

    summary = {
        "n": n, "class_accuracy": round(correct / n, 3), "class_accuracy_ci95": wilson(correct, n),
        "false_validation": false_validation,                       # must be 0
        "n_positive": len(positives), "positives_found_grounded": pos_found,
        "n_negative": len(negatives), "negatives_abstained": sum(1 for r in negatives if r["verdict"] == "NO_VALIDATION_FOUND"),
        "expected_citation_hits": f"{exp_hit}/{len(with_exp)}",
        "rows": rows,
    }
    json.dump(summary, open("benchmark/repro/investigate_eval.json", "w"), indent=1)

    print(f"=== Agentic Investigator — measured eval (n={n}, live PubMed+Cellosaurus) ===\n")
    print(f"{'id':<6}{'name':<38}{'expect':<20}{'verdict':<20}{'grounded':<9}{'cited'}")
    for r in rows:
        print(f"{r['id']:<6}{r['name'][:36]:<38}{r['expect']:<20}{r['verdict']:<20}"
              f"{str(r['grounded']):<9}{','.join(r['cited'])[:40]}")
    ci = summary["class_accuracy_ci95"]
    print(f"\nclass accuracy: {correct}/{n} = {correct / n:.0%}  (Wilson 95% CI {ci[0]:.0%}-{ci[1]:.0%})")
    print(f"false-validation (negative wrongly 'validated' — the costly error): {false_validation}")
    print(f"positives found+grounded: {pos_found}/{len(positives)} · negatives abstained: {summary['negatives_abstained']}/{len(negatives)}")
    print(f"expected-citation hits (right real record cited): {exp_hit}/{len(with_exp)}")


if __name__ == "__main__":
    main()
