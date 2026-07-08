"""Ablation study: does each evidence signal earn its place in the engine?

For each signal we neutralize it at the data boundary (deterministically) across all
labeled claims and measure the accuracy hit + any confidently-wrong calls it introduces.
A signal that matters shows a drop when removed; one that doesn't is dead weight.
"""
from __future__ import annotations

import dataclasses
import os

from verdict.corpora import available, load_path, load_rows
from verdict.gates import EvidenceRow, resolve

ROOT = os.path.dirname(os.path.dirname(__file__))
RETIRED = {"C09", "F02"}


def _labeled():
    items = []
    for cid in available():
        if cid in RETIRED:
            continue
        m, rows = load_rows(cid)
        items.append((rows, m["expected_verdict"]))
    for sub in ("heldout", "heldout_v2", "heldout_v3"):
        d = os.path.join(ROOT, "benchmark", sub)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".json"):
                    m, rows = load_path(os.path.join(d, f))
                    items.append((rows, m["expected_verdict"]))
    return items


def _mut(rows, **over):
    return [dataclasses.replace(r, **over) for r in rows]


ABLATIONS = {
    "baseline (full engine)": lambda rows: rows,
    "no integrity screen (keep retracted)": lambda rows: _mut(rows, integrity_ok=True),
    "no outcome-directness (surrogate=outcome)": lambda rows: _mut(rows, outcome_match=True),
    "no all-or-none path": lambda rows: _mut(rows, dramatic_effect=False),
    "no population filter": lambda rows: _mut(rows, population_match=True),
}


def main() -> None:
    items = _labeled()
    n = len(items)
    print(f"=== ablation over {n} labeled claims (benchmark + held-out) ===\n")
    print(f"  {'ablation':<44}{'accuracy':>10}{'conf-wrong':>12}")
    base_acc = None
    for name, fn in ABLATIONS.items():
        ok = cw = 0
        for rows, gold in items:
            v = resolve(fn(rows))[0].value
            ok += v == gold
            cw += gold in ("Not Supported", "Insufficient") and v == "Supported"
        acc = ok / n
        if base_acc is None:
            base_acc = acc
            delta = ""
        else:
            delta = f"  ({(acc - base_acc) * 100:+.1f} pts)"
        print(f"  {name:<44}{acc:>9.0%}{cw:>12}{delta}")


if __name__ == "__main__":
    main()
