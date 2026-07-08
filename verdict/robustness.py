"""Verdict robustness: does the call survive perturbing the evidence?

A verdict you can trust should not hinge on one study. For a resolved claim we drop
each contributing study in turn and re-resolve; the robustness score is the fraction
of single-study removals that leave the verdict unchanged, and we separately flag
whether the verdict survives dropping the single largest (most influential) trial.
Deterministic, no LLM — it just re-runs the gate engine.
"""
from __future__ import annotations

from dataclasses import dataclass

from .gates import EvidenceRow, resolve


@dataclass
class Robustness:
    verdict: str
    stability: float           # fraction of single-study drops that preserve the verdict
    survives_drop_largest: bool
    n_perturbations: int
    flips: list[str]           # source_ids whose removal changes the verdict


def robustness(rows: list[EvidenceRow]) -> Robustness:
    base = resolve(rows)[0].value
    # Only integrity-ok rows can influence the verdict; perturbing an already-excluded
    # (retracted) row is meaningless.
    live = [r for r in rows if r.integrity_ok]
    flips: list[str] = []
    for i, r in enumerate(live):
        held = [x for j, x in enumerate(live) if j != i]
        # Dropping to nothing resolves to Insufficient — a verdict resting on one study is,
        # correctly, not robust to that study's removal.
        if resolve(held)[0].value != base:
            flips.append(r.source_id or r.citation[:40])
    n = max(1, len(live))
    stability = round((len(live) - len(flips)) / n, 3)

    survives_largest = True
    trials = [r for r in live if r.is_trial and r.n_int]
    if trials:
        largest = max(trials, key=lambda r: r.n_int)
        held = [x for x in live if x is not largest]
        survives_largest = bool(held) and resolve(held)[0].value == base

    return Robustness(base, stability, survives_largest, len(live), flips)
