"""Knockout-control validation — the ONE gate where Claude REASONS, not just extracts.

Antibody identity (catalog# -> RRID) is a deterministic lookup. But an RRID does not tell you the
antibody was VALIDATED for specificity in *this* study. The gold-standard validation is a genetic
control: a knockout / knockdown / CRISPR / siRNA showing the signal disappears when the target is
removed. Whether a Methods section actually DESCRIBES such a control — versus claiming "validated"
with no evidence, versus a weaker non-genetic control (peptide competition, secondary-only) — is a
reasoning judgment, not a keyword match.

This gate asks Claude to reason about exactly that, and returns a LABELLED model judgment:
  validated     -> PASS          a genetic KO/KD/CRISPR/siRNA control for this antibody is described
  ambiguous     -> INSUFFICIENT  validation is claimed/implied, but not a genetic control (or unclear)
  not_reported  -> INSUFFICIENT  no antibody-specificity validation is described

It never issues a deterministic verdict and never FAILs (absence of a control is not a citable defect
the way a register hit is) — aggregate() treats it as advisory. This is the deliberate counterpart to
the deterministic gates: the one place the model's *reasoning* is the product, honestly labelled.
"""
from __future__ import annotations

from dataclasses import dataclass

from .parse import call_tool

_KNOCKOUT_TOOL = {
    "name": "assess_knockout_validation",
    "description": "Judge whether a Methods section describes a GENETIC knockout / knockdown / CRISPR / "
                   "siRNA control validating a named antibody's specificity.",
    "input_schema": {"type": "object", "properties": {
        "status": {"type": "string", "enum": ["validated", "ambiguous", "not_reported"],
                   "description": "validated = a genetic KO/KD/CRISPR/siRNA control showing signal loss is "
                                  "described for THIS antibody; ambiguous = validation is claimed/implied "
                                  "but not a genetic control, or it is unclear which antibody it applies "
                                  "to; not_reported = no specificity validation is described"},
        "evidence": {"type": "string", "description": "the verbatim phrase describing the control, or empty"},
        "reasoning": {"type": "string", "description": "one sentence: why this status"}},
        "required": ["status", "evidence", "reasoning"]},
}

_KNOCKOUT_SYSTEM = (
    "You are an antibody-validation reviewer. The GOLD STANDARD for antibody specificity is a GENETIC "
    "control: an in-study knockout, knockdown, CRISPR, or siRNA experiment showing the antibody signal "
    "DISAPPEARS when the target protein is removed. Peptide competition, pre-adsorption, overexpression, "
    "secondary-only / primary-omission controls, isotype controls, manufacturer validation, or a bare claim "
    "of 'validated' / 'specific' are NOT in-study genetic controls. A knockout of a DIFFERENT protein than "
    "the named antibody's target does not validate it. Validation merely CITED from a prior paper was not "
    "performed in this study. Reason about whether the Methods describe an in-study genetic control for the "
    "NAMED antibody's own target, and return the status. Quote the verbatim phrase in evidence. Do not infer "
    "a control that is not described; when between 'validated' and something weaker, choose 'ambiguous'.\n"
    "Examples of the judgment (illustrative — reason from the text in front of you, not these):\n"
    "- 'anti-PSD-95 ... confirmed in PSD-95-knockout neurons, which showed no signal' -> validated "
    "(in-study genetic control for the same target, signal lost).\n"
    "- 'specificity of anti-HIF1alpha verified by HIF1A siRNA knockdown, abolishing the band' -> validated.\n"
    "- 'a specific, previously characterised antibody was used' -> ambiguous (bare claim, no control described).\n"
    "- 'anti-VIP specificity confirmed by pre-adsorption with the antigen' -> ambiguous (a control, but not genetic).\n"
    "- 'anti-Calbindin, validated by knockout in ref [12], was used' -> ambiguous (validation cited, not performed here).\n"
    "- 'anti-Kv1.1 specificity assessed in Kv1.2-knockout mice' -> ambiguous (knockout of the WRONG target).\n"
    "- 'sections were stained with anti-MAP2 (Sigma, M4403; 1:1000)' with nothing further -> not_reported.\n"
    "- 'a no-primary-antibody control yielded no signal' -> not_reported "
    "(secondary-only control does not validate the primary's specificity)."
)

_VALID = ("validated", "ambiguous", "not_reported")


@dataclass
class KnockoutFinding:
    antibody: str
    status: str       # "validated" | "ambiguous" | "not_reported"
    result: str       # "PASS" | "INSUFFICIENT"  — never FAIL
    detail: str
    evidence: str = ""
    method: str = "model judgment"


def _finding(status: str, antibody: str, evidence: str) -> KnockoutFinding:
    if status == "validated":
        return KnockoutFinding(
            antibody, "validated", "PASS",
            "A genetic knockout/knockdown control validating this antibody's specificity is described.",
            evidence)
    if status == "ambiguous":
        return KnockoutFinding(
            antibody, "ambiguous", "INSUFFICIENT",
            "Validation is claimed or implied, but no genetic (knockout/knockdown/CRISPR/siRNA) control is "
            "clearly described — verify the antibody was validated for specificity.", evidence)
    return KnockoutFinding(
        antibody, "not_reported", "INSUFFICIENT",
        "No antibody-specificity validation (e.g. a knockout/knockdown control) is described — add one or "
        "cite prior genetic validation.", evidence)


def assess_knockout_control(methods_text: str, antibody: str) -> KnockoutFinding:
    """Reason (via Claude) about whether the Methods describe a genetic knockout/knockdown control
    validating `antibody`. Returns a LABELLED model judgment; degrades to not_reported on any error."""
    try:
        d = call_tool(_KNOCKOUT_SYSTEM, f"Antibody: {antibody}\n\nMethods:\n\n{methods_text}",
                      _KNOCKOUT_TOOL, max_tokens=400)
    except Exception:  # noqa: BLE001 — degrade gracefully, never crash the review
        d = {}
    status = d.get("status", "not_reported")
    if status not in _VALID:
        status = "not_reported"
    return _finding(status, antibody, str(d.get("evidence", "")))
