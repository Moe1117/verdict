"""Deterministic verdict engine — NO LLM in the verdict path.

Every verdict is a pure function of the extracted evidence rows and the gate
outcomes, so it is fully auditable: same rows in, same verdict + same gate trace
out, always. The LLM's only job (elsewhere) is to produce the rows.

The resolution mirrors how evidence-based medicine actually adjudicates a claim:
1. drop studies with a documented integrity problem (retraction / EoC);
2. require genuine trial-grade human evidence (RCT / meta-of-RCTs / target-trial)
   on-population — otherwise the evidence is ABSENT (Insufficient), not against;
3. if that evidence agrees, return Supported / Not Supported;
4. if it conflicts, let the DEFINITIVE tier decide — large clean RCTs first, then
   recent meta-analyses — and only call Contested when the definitive tier itself
   genuinely conflicts.
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

# Trial-grade human evidence. A (narrative/observational) "systematic review" is
# deliberately EXCLUDED: on its own it does not establish a randomized effect.
TRIAL_DESIGNS = {"meta-analysis of rcts", "target-trial emulation", "rct"}

LARGE_RCT_N = 1000      # an RCT at/above this is "large" — decisive when trials conflict
RECENT_META_WINDOW = 4  # years back from the newest meta counted as "current"


@dataclass
class EvidenceRow:
    citation: str
    design: str                  # a key of DESIGN_WEIGHT (normalized upstream)
    direction: int               # +1 supports, -1 contradicts, 0 null/no-effect
    population_match: bool        # does the study population match the claim?
    source_id: str = ""          # PMID / NCT / DOI
    integrity_ok: bool = True     # False when a citable retraction/EoC applies (see integrity.py)
    n: str = ""                   # sample size (display)
    n_int: int = 0                # sample size (numeric, for the large-RCT rule)
    year: int = 0                 # publication year (numeric, for recency)
    finding: str = ""             # one-line finding (display; our words, no verbatim abstract)
    integrity_note: str = ""      # why integrity_ok is False, with a citable source
    note: str = ""

    @property
    def weight(self) -> int:
        return DESIGN_WEIGHT.get(self.design.strip().lower(), 0)

    @property
    def is_trial(self) -> bool:
        return self.design.strip().lower() in TRIAL_DESIGNS

    @property
    def is_meta(self) -> bool:
        return self.design.strip().lower() == "meta-analysis of rcts"

    @property
    def is_rct(self) -> bool:
        return self.design.strip().lower() == "rct"

    @property
    def supports(self) -> bool:
        return self.direction == 1

    @property
    def against(self) -> bool:  # contradicts or shows no effect
        return self.direction in (-1, 0)


@dataclass
class GateTrace:
    gate: str
    passed: bool
    detail: str


def resolve(rows: list[EvidenceRow]) -> tuple[Verdict, list[GateTrace]]:
    """Return (verdict, gate_trace). Deterministic; no LLM, no randomness."""
    trace: list[GateTrace] = []

    # Gate 0 — integrity screen: drop studies with a documented retraction / EoC.
    dropped = [r for r in rows if not r.integrity_ok]
    rows = [r for r in rows if r.integrity_ok]
    if dropped:
        trace.append(GateTrace("integrity-screen", True,
                               f"excluded {len(dropped)} study(ies) with documented integrity concerns"))

    # Gate 1 — trial-grade human evidence on-population?
    trials = [r for r in rows if r.is_trial and r.population_match]
    if not trials:
        trace.append(GateTrace("direct-evidence", False,
                               "no on-population randomized/meta evidence — absence of evidence"))
        return Verdict.INSUFFICIENT, trace
    trace.append(GateTrace("direct-evidence", True,
                           f"{len(trials)} trial-grade on-population study(ies)"))

    pros = [r for r in trials if r.supports]
    cons = [r for r in trials if r.against]

    # Gate 2 — consistency.
    if not cons:
        trace.append(GateTrace("consistency", True, "trial evidence agrees: effect present"))
        return Verdict.SUPPORTED, trace
    if not pros:
        trace.append(GateTrace("consistency", True,
                               "trial evidence agrees: no effect (evidence of absence)"))
        return Verdict.NOT_SUPPORTED, trace

    # Gate 3 — trial evidence conflicts: let the definitive tier decide.
    large = [r for r in trials if r.is_rct and r.n_int >= LARGE_RCT_N]
    if large:
        if all(r.against for r in large):
            trace.append(GateTrace("definitive-evidence", True,
                                   f"{len(large)} large RCT(s) show no effect; positive signal is smaller/older"))
            return Verdict.NOT_SUPPORTED, trace
        if all(r.supports for r in large):
            trace.append(GateTrace("definitive-evidence", True, f"{len(large)} large RCT(s) show the effect"))
            return Verdict.SUPPORTED, trace
        trace.append(GateTrace("definitive-evidence", False, "large RCTs themselves conflict"))
        return Verdict.CONTESTED, trace

    metas = [r for r in trials if r.is_meta and r.year]
    if metas:
        newest = max(r.year for r in metas)
        recent = [r for r in metas if r.year >= newest - RECENT_META_WINDOW]
        if all(r.against for r in recent):
            trace.append(GateTrace("definitive-evidence", True, "recent meta-analyses agree: no effect"))
            return Verdict.NOT_SUPPORTED, trace
        if all(r.supports for r in recent):
            trace.append(GateTrace("definitive-evidence", True, "recent meta-analyses agree: effect present"))
            return Verdict.SUPPORTED, trace
        trace.append(GateTrace("definitive-evidence", False,
                               "recent high-quality evidence genuinely conflicts"))
        return Verdict.CONTESTED, trace

    trace.append(GateTrace("consistency", False, "trial evidence conflicts with no dominant tier"))
    return Verdict.CONTESTED, trace
