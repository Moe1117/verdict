"""Effect-magnitude classification — so the engine can reason on effect SIZE, not just sign.

Direction alone can't tell a large effect from a marginal one, or a precise null from an
underpowered one. Where the extractor reports an effect estimate + CI + significance, each
row is classified against a DECLARED minimal-important-difference (MID) — thresholds set
from the clinical/regulatory literature, NOT fit to the labels. This drives two asymmetric
rules in the gate engine:
  (A) a significant, MID-clearing effect can settle a conflict that is otherwise just a real
      effect vs an underpowered (wide, non-significant) null — a wide null is absence of a
      signal, not counter-evidence; and
  (B) a statistically-significant but SUB-MID (marginal) effect may never become a confident
      Supported — it is capped at Contested. (B) is the safety half: it can only ever make the
      engine MORE cautious, so it cannot erode 'never confidently wrong'.

MID rationale (ratio scale, HR/RR/OR): an effect is 'meaningful' only if significant AND at
least a ~10% relative effect (point estimate <=0.90 or >=1.11). Sub-10% relative effects on
hard outcomes are conventionally treated as marginal (GRADE imprecision; regulatory
'clinically meaningful' conventions). Absolute-scale (mean/proportion difference) MIDs are
outcome-specific; absent a per-outcome table we treat a significant absolute effect as
meaningful and flag the limitation.
"""
from __future__ import annotations

from .gates import EvidenceRow

RATIO_MID_LOW = 0.90    # HR/RR/OR at or below this (>=10% relative reduction) = meaningful
RATIO_MID_HIGH = 1.11   # at or above this (>=~10% relative increase) = meaningful


def effect_strength(r: EvidenceRow) -> str:
    """Classify a row's effect:
      'meaningful'  — significant AND clears the MID (a real, clinically-relevant effect)
      'marginal'    — significant but sub-MID (real but small; may never become confident yes)
      'precise_null'— non-significant with a CI tight enough to RULE OUT a meaningful effect
                      (genuine evidence of no effect — a real contradiction)
      'wide_null'   — non-significant with a CI that still admits a meaningful effect
                      (absence of a signal, NOT counter-evidence)
      'unknown'     — no usable magnitude info -> engine falls back to sign-only logic.
    """
    if r.sig == "significant" and r.effect_point is not None:
        if r.effect_scale == "ratio":
            return "meaningful" if (r.effect_point <= RATIO_MID_LOW or r.effect_point >= RATIO_MID_HIGH) else "marginal"
        return "meaningful"  # absolute scale: per-outcome MID would refine
    if r.sig == "nonsignificant":
        if (r.effect_scale == "ratio" and r.ci_low is not None and r.ci_high is not None
                and r.ci_low >= RATIO_MID_LOW and r.ci_high <= RATIO_MID_HIGH):
            return "precise_null"  # CI brackets the null tightly -> genuinely no meaningful effect
        return "wide_null"
    return "unknown"


def has_magnitude(rows: list[EvidenceRow]) -> bool:
    """Does any row carry usable magnitude info? Gates that read magnitude no-op otherwise."""
    return any(effect_strength(r) != "unknown" for r in rows)
