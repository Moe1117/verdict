"""Orchestration: claim -> verdict card.

parse -> retrieve -> extract -> integrity-screen -> deterministic gates -> calibrate.
The LLM touches parse and extract only; the verdict itself comes from gates.py.

`evaluate()` works on any list of rows. `run_frozen()` runs it over the frozen,
verified demo corpora (no network, no LLM) — the deterministic demo path.
"""
from __future__ import annotations

from dataclasses import dataclass

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
    """Given extracted evidence rows, produce the auditable verdict card."""
    verdict, trace = resolve(rows)
    return VerdictCard(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        ledger=rows,
        gate_trace=trace,
    )


def run_frozen(claim_id: str) -> VerdictCard:
    """Resolve a claim from the frozen demo corpora (deterministic, offline)."""
    from .corpora import load_rows

    meta, rows = load_rows(claim_id)
    return evaluate(meta.get("claim", claim_id), rows)
