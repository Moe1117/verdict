"""Deterministic verdict engine — NO LLM in the verdict path.

Every verdict is a pure function of the extracted evidence rows and the gate
outcomes, so it is fully auditable. This module is the core differentiator of
Verdict: given the same rows, it always returns the same verdict and the same
gate trace. The LLM's only job (elsewhere) is to produce the rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    SUPPORTED = "Supported"
    NOT_SUPPORTED = "Not Supported"
    CONTESTED = "Contested"
    INSUFFICIENT = "Insufficient"
    # Input guard only — for ill-posed / unmeasurable claims. Never an evidence verdict.
    UNDECIDABLE = "Undecidable"


# Study design tiers, highest evidence weight to lowest.
DESIGN_WEIGHT = {
    "meta-analysis of rcts": 5,
    "target-trial emulation": 5,
    "systematic review": 4,
    "rct": 4,
    "prospective cohort": 3,
    "case-control": 2,
    "cross-sectional": 2,
    "case report": 1,
    "preclinical": 0,  # animal / in-vitro — never sufficient for a human efficacy claim
}
HIGH_TIER = 4  # weight >= HIGH_TIER counts as decisive human evidence


@dataclass
class EvidenceRow:
    citation: str
    design: str                  # a key of DESIGN_WEIGHT (normalized upstream)
    direction: int               # +1 supports, -1 contradicts, 0 null/no-effect
    population_match: bool        # does the study population match the claim?
    source_id: str = ""          # PMID / NCT / DOI
    integrity_ok: bool = True     # False when a citable retraction/EoC applies (see integrity.py)
    note: str = ""

    @property
    def weight(self) -> int:
        return DESIGN_WEIGHT.get(self.design.strip().lower(), 0)


@dataclass
class GateTrace:
    gate: str
    passed: bool
    detail: str


def resolve(rows: list[EvidenceRow]) -> tuple[Verdict, list[GateTrace]]:
    """Return (verdict, gate_trace). Deterministic; no LLM, no randomness."""
    trace: list[GateTrace] = []

    # Integrity screen — drop studies with a documented retraction / EoC.
    dropped = [r for r in rows if not r.integrity_ok]
    rows = [r for r in rows if r.integrity_ok]
    if dropped:
        trace.append(GateTrace("integrity-screen", True,
                               f"excluded {len(dropped)} study(ies) with documented integrity concerns"))

    # Gate 1 — direct human evidence: at least one on-population RCT/meta.
    high = [r for r in rows if r.weight >= HIGH_TIER and r.population_match]
    if not high:
        trace.append(GateTrace("direct-evidence", False,
                               "no on-population RCT or meta-analysis — absence of evidence"))
        return Verdict.INSUFFICIENT, trace
    trace.append(GateTrace("direct-evidence", True,
                           f"{len(high)} high-tier on-population study(ies)"))

    # Gate 2 — consistency of direction among high-tier evidence.
    directions = {r.direction for r in high}
    if directions == {1}:
        trace.append(GateTrace("consistency", True, "high-tier evidence agrees: effect present"))
        return Verdict.SUPPORTED, trace
    if directions <= {-1, 0}:  # all null and/or contradicting
        trace.append(GateTrace("consistency", True,
                               "high-tier evidence agrees: no effect (evidence of absence)"))
        return Verdict.NOT_SUPPORTED, trace

    # Mixed high-tier directions -> genuine conflict.
    trace.append(GateTrace("consistency", False, "high-tier evidence conflicts"))
    return Verdict.CONTESTED, trace
