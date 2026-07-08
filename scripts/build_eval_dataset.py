"""Reproducibly assemble the plain-LLM cold-set eval dataset from the frozen corpora and
score it — the single command behind web/public/eval.json (the headline scorecard).

Single source of truth: benchmark/corpora/*.json, each carrying rows + expected_verdict +
an inline `baseline` (the confident plain-LLM answer the engine is measured against). C09/F02
are retired from the clinical benchmark. This makes the scorecard regenerable from a clone:

    PYTHONPATH=. python scripts/build_eval_dataset.py

It fails loudly if any corpus lacks a baseline, so the scorecard can never silently drift out
of reproducibility again. Deterministic; the assembly + gate scoring use no network and no LLM.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile

from verdict.corpora import available, load_rows

sys.path.insert(0, os.path.dirname(__file__))
import eval as eval_mod  # scripts/eval.py — the SINGLE scoring path (Verdict / naive / plain-LLM)

RETIRED = {"C09", "F02"}  # fringe/supplement, not part of the clinical benchmark


def build_dataset() -> dict:
    """Assemble {"dataset": [...]} from every non-retired corpus (rows + gold + baseline)."""
    items = []
    for cid in available():
        if cid in RETIRED:
            continue
        meta, rows = load_rows(cid)
        if "baseline" not in meta or "expected_verdict" not in meta:
            raise SystemExit(f"corpus {cid} is missing baseline/expected_verdict — cannot "
                             "assemble the eval dataset reproducibly (add an inline baseline)")
        items.append({
            "id": cid,
            "claim": meta["claim"],
            "rows": [dataclasses.asdict(r) for r in rows],
            "gold": {"verdict": meta["expected_verdict"]},
            "baseline": meta["baseline"],
        })
    return {"dataset": items}


def main() -> None:
    data = build_dataset()
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        with open(path, "w") as fh:
            json.dump(data, fh)
        eval_mod.main(path, "eval.json")  # scores + writes web/public/eval.json
    finally:
        os.remove(path)
    print(f"\nassembled {len(data['dataset'])} claims from benchmark/corpora/ -> web/public/eval.json")


if __name__ == "__main__":
    main()
