"""Deterministic GRADE-inspired certainty for each verdict.

Every verdict carries not just a state but a certainty level — High / Moderate /
Low / Very Low — computed as a pure function of the same evidence rows, with an
auditable list of the signals that drove it. This mirrors how GRADE grades the
CERTAINTY of a body of evidence: start from the study design tier, then adjust for
precision and the decision context. It is deterministic (no LLM) and it is what the
calibration layer (calibrate.py) empirically validates.

Not a full formal GRADE assessment (risk-of-bias / publication-bias judgements need a
human); it is a reproducible, defensible approximation from the structured fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .gates import EvidenceRow, LARGE_RCT_N, Verdict

LEVELS = ["Very Low", "Low", "Moderate", "High"]  # index == score 0..3


@dataclass
class Certainty:
    level: str            # one of LEVELS
    score: int            # 0..3
    signals: list[str] = field(default_factory=list)  # auditable drivers


def _deciding(rows: list[EvidenceRow]) -> list[EvidenceRow]:
    """The rows the verdict actually rested on: integrity-ok, on-population, on-outcome."""
    return [r for r in rows if r.integrity_ok and r.population_match and r.outcome_match]


def grade_certainty(rows: list[EvidenceRow], verdict: Verdict) -> Certainty:
    if verdict is Verdict.INSUFFICIENT:
        return Certainty("Very Low", 0, ["no decision-grade on-outcome evidence (absence / indirectness)"])
    if verdict is Verdict.CONTESTED:
        return Certainty("Low", 1, ["decision-grade evidence genuinely conflicts"])

    deciding = _deciding(rows)
    trials = [r for r in deciding if r.is_trial]
    metas = [r for r in trials if r.is_meta]
    rcts = [r for r in trials if r.is_rct]
    large = [r for r in rcts if r.n_int >= LARGE_RCT_N]
    dramatic = [r for r in deciding if r.dramatic_effect]
    total_n = sum(r.n_int for r in trials if r.n_int)

    signals: list[str] = []
    if metas:
        score, why = 3, f"{len(metas)} meta-analysis(es) of RCTs"
    elif large or len(rcts) >= 2:
        score, why = 3, f"{len(large) or len(rcts)} {'large ' if large else ''}RCT(s)"
    elif rcts:
        score, why = 2, "a single sub-large RCT"
    elif dramatic:
        score, why = 2, "all-or-none / dramatic effect (single-arm, upgraded)"
    else:
        score, why = 1, "non-randomized evidence only"
    signals.append(f"base: {why}")

    # Imprecision: no meta, no large RCT, and a small total evidence base.
    if not metas and not large and total_n and total_n < 500:
        score -= 1
        signals.append("imprecision: no meta / no large RCT, small total N (−1)")

    # Effect magnitude: a SUPPORTED verdict that rests on a statistically-significant but
    # SUB-MID (marginal) effect — with no clinically meaningful effect behind it — is less
    # certain. (A null is the correct evidence for Not Supported, so this applies only to the
    # positive direction.) Confidence only, never the verdict.
    from .magnitude import effect_strength, has_magnitude
    if verdict is Verdict.SUPPORTED:
        pros = [r for r in trials if r.supports]
        if has_magnitude(pros):
            strengths = {effect_strength(r) for r in pros}
            if "meaningful" not in strengths and "marginal" in strengths:
                score -= 1
                signals.append("magnitude: the supporting effect is significant but sub-clinical (marginal) (−1)")

    score = max(0, min(3, score))
    return Certainty(LEVELS[score], score, signals)
