"""Verdict over time — replay a claim as its evidence accrued.

A verdict is a pure function of its evidence; run that function over only the studies that
existed by year Y, sweeping Y, and you get the trajectory of the claim through history — the
moment the science turned. This is how ivermectin goes Insufficient -> Supported (early hype)
-> Contested -> Not Supported as the clean RCTs land, and how a real drug goes Insufficient ->
Supported the moment its pivotal trial reports.

Strictly additive: it only ever calls resolve() on subsets of the rows, so it can never change
a verdict. Undated rows (year == 0) cannot be placed on the timeline and are excluded from the
sweep; the final dated timepoint therefore equals the current verdict over the dated evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from .certainty import grade_certainty
from .gates import EvidenceRow, resolve


@dataclass
class Timepoint:
    year: int
    verdict: str        # the verdict using only evidence available by this year
    certainty: str      # GRADE certainty level at this point
    certainty_score: int
    n_studies: int      # cumulative dated studies available by this year
    changed: bool       # the verdict differs from the previous timepoint (a turn)


def verdict_over_time(rows: list[EvidenceRow]) -> list[Timepoint]:
    """The verdict trajectory across the distinct publication years of the dated evidence."""
    dated = [r for r in rows if r.year and r.year > 0]
    out: list[Timepoint] = []
    prev: str | None = None
    for year in sorted({r.year for r in dated}):
        sub = [r for r in dated if r.year <= year]
        verdict = resolve(sub)[0]
        cert = grade_certainty(sub, verdict)
        out.append(Timepoint(
            year=year, verdict=verdict.value, certainty=cert.level,
            certainty_score=cert.score, n_studies=len(sub), changed=(verdict.value != prev),
        ))
        prev = verdict.value
    return out
