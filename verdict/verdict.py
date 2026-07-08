"""Orchestration: claim -> verdict card.

parse -> retrieve -> extract -> integrity-screen -> deterministic gates -> calibrate.
The LLM touches parse and extract only; the verdict itself comes from gates.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import DISCLAIMER
from .gates import EvidenceRow, GateTrace, Verdict, resolve


@dataclass
class VerdictCard:
    claim: str
    verdict: Verdict
    confidence: float | None
    ledger: list[EvidenceRow]
    gate_trace: list[GateTrace]
    what_would_change_it: str = ""
    disclaimer: str = DISCLAIMER


def evaluate(claim: str, rows: list[EvidenceRow], confidence: float | None = None) -> VerdictCard:
    """Given extracted evidence rows, produce the auditable verdict card.

    (Wiring parse/retrieve/extract into this is the next build step; the
    deterministic core below already works on real rows.)
    """
    verdict, trace = resolve(rows)
    return VerdictCard(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        ledger=rows,
        gate_trace=trace,
    )
