"""Deterministic GRADE-inspired certainty for each verdict — as a full per-domain profile.

Every verdict carries not just a state but a certainty level — High / Moderate / Low /
Very Low — computed as a pure function of the same evidence rows. This module now emits
the *derivation* the way a GRADE evidence profile does: a starting tier from study design,
then an explicit up/down-grade across each GRADE domain —

    risk of bias · inconsistency · indirectness · imprecision · publication bias
    (+ the large-effect upgrade)

— each carrying a signed delta and a plain-language rationale, so the final certainty is a
transparent sum:  certainty_score = clamp(start_tier + Σ domain deltas).

It is deterministic (no LLM) and it is what the calibration layer (calibrate.py) empirically
validates. Domains that require human judgement to assess honestly — per-study risk of bias,
publication bias — are reported explicitly as "not automated / not assessed, no downgrade
applied" rather than silently omitted.

This is a behaviour-preserving re-expression of the prior scorer: the certainty SCORE for any
evidence set is unchanged (proved in tests/test_grade_profile.py against a frozen legacy
oracle), so the validated calibration cannot move. What is new is the auditable breakdown.

Not a full formal GRADE assessment (per-study risk-of-bias / publication-bias judgements need
a human); it is a reproducible, defensible approximation from the structured fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .gates import EvidenceRow, LARGE_RCT_N, Verdict

LEVELS = ["Very Low", "Low", "Moderate", "High"]  # index == score 0..3

# The five core GRADE certainty domains, in canonical order. Every verdict's profile
# reports all five; the large-effect UPGRADE is added only when it applies.
CORE_DOMAINS = ("risk of bias", "inconsistency", "indirectness", "imprecision", "publication bias")


@dataclass
class GradeDomain:
    name: str          # a CORE_DOMAINS entry, or "large effect" (upgrade)
    delta: int         # GRADE step: -2 very serious, -1 serious, 0 none, +1/+2 upgrade
    rationale: str     # plain-language reason for the delta


@dataclass
class Certainty:
    level: str                    # one of LEVELS
    score: int                    # 0..3
    signals: list[str] = field(default_factory=list)   # auditable drivers (backward-compat)
    start: int = 0                # starting tier score (0..3) before domain adjustments
    start_label: str = "Very Low"  # human label for the start tier
    domains: list[GradeDomain] = field(default_factory=list)  # per-domain GRADE profile


def _deciding(rows: list[EvidenceRow]) -> list[EvidenceRow]:
    """The rows the verdict actually rested on: integrity-ok, on-population, on-outcome."""
    return [r for r in rows if r.integrity_ok and r.population_match and r.outcome_match and r.dose_match]


def _signals(start_label: str, domains: list[GradeDomain]) -> list[str]:
    """Readable audit summary (kept for export_cards.py / the web card)."""
    out = [f"start: {start_label} certainty from study design"]
    out += [f"{d.name}: {d.rationale} ({'+' if d.delta > 0 else ''}{d.delta})"
            for d in domains if d.delta != 0]
    if len(out) == 1:
        out.append("no per-domain adjustments applied")
    return out


def _assemble(start: int, domains: list[GradeDomain]) -> Certainty:
    score = max(0, min(3, start + sum(d.delta for d in domains)))
    start_label = LEVELS[max(0, min(3, start))]
    return Certainty(LEVELS[score], score, _signals(start_label, domains),
                     start=start, start_label=start_label, domains=domains)


def grade_certainty(rows: list[EvidenceRow], verdict: Verdict) -> Certainty:
    # --- Verdict-level floors, expressed as GRADE profiles ---------------------------------
    if verdict is Verdict.UNDECIDABLE:
        # Input-guard rejection: the claim was never posed as a measurable question, so there is
        # no evidence body to grade. Emit an EMPTY profile — grading nothing would be fabrication.
        return _assemble(0, [])

    if verdict is Verdict.INSUFFICIENT:
        # No gradable body of decision-grade evidence: the profile records WHY there is
        # nothing to grade (absence / indirectness), and every domain is 0 -> Very Low.
        domains = [
            GradeDomain("risk of bias", 0, "no decision-grade trial evidence to appraise"),
            GradeDomain("inconsistency", 0, "no decision-grade trial evidence to compare"),
            GradeDomain("indirectness", 0, "the available evidence is absent, off-population, off-dose, "
                        "or measures only a surrogate — it cannot directly address the claim"),
            GradeDomain("imprecision", 0, "no decision-grade trial evidence to weigh for precision"),
            GradeDomain("publication bias", 0, "not assessable without a body of studies"),
        ]
        return _assemble(0, domains)

    if verdict is Verdict.CONTESTED:
        # Decision-grade evidence exists on both sides but genuinely conflicts: in GRADE terms
        # a very-serious INCONSISTENCY downgrade from the RCT-grade start (3 - 2 = Low).
        domains = [
            GradeDomain("risk of bias", 0, "decision-grade (randomized / meta-analytic) evidence on both sides"),
            GradeDomain("inconsistency", -2, "decision-grade evidence genuinely conflicts and the definitive "
                        "tier does not resolve it — the reason this claim is Contested"),
            GradeDomain("indirectness", 0, "the conflicting evidence is on-population and on the claimed outcome"),
            GradeDomain("imprecision", 0, "the conflict is directional, not a precision artefact"),
            GradeDomain("publication bias", 0, "not separately assessed"),
        ]
        return _assemble(3, domains)

    # --- Decided verdicts (Supported / Not Supported): start from study design, then adjust --
    deciding = _deciding(rows)
    trials = [r for r in deciding if r.is_trial]
    metas = [r for r in trials if r.is_meta]
    rcts = [r for r in trials if r.is_rct]
    large = [r for r in rcts if r.n_int >= LARGE_RCT_N]
    dramatic = [r for r in deciding if r.dramatic_effect]
    total_n = sum(r.n_int for r in trials if r.n_int)
    randomized = bool(metas) or bool(rcts)  # RCT or meta-of-RCTs present

    domains: list[GradeDomain] = []

    # Evidence-quality cap (risk of bias): the engine reasons on study DESIGN TIER but cannot see
    # the quality of the trials pooled inside a meta-analysis. A LONE, unreplicated meta — one
    # meta, no corroborating large RCT, fewer than two primary RCTs — is exactly where
    # pooling-of-junk hides (how, replaying history, a 2021 meta built on later-flagged ivermectin
    # trials read as High-certainty). Replication (a second concordant meta, a large primary RCT,
    # or >=2 primary RCTs) earns High; a lone synthesis is capped below it. Certainty-only.
    lone_synthesis = len(metas) == 1 and not large and len(rcts) < 2

    # Start tier (GRADE: randomized evidence starts High; otherwise observational-grade Low).
    if randomized:
        start = 3
        if lone_synthesis:
            rob_delta = -1
            rob_reason = ("rests on a single meta-analysis with no corroborating large RCT — the "
                          "pooled trials' quality is unverified and unreplicated, so certainty is "
                          "capped below High (a second concordant meta or a large RCT would earn it)")
        else:
            rob_delta = 0
            design_bits = []
            if metas:
                design_bits.append(f"{len(metas)} meta-analysis(es) of RCTs")
            if large:
                design_bits.append(f"{len(large)} large RCT(s)")
            elif rcts:
                design_bits.append(f"{len(rcts)} RCT(s)")
            rob_reason = ("randomized evidence (" + ", ".join(design_bits) + ") — starts at High; "
                          "per-study risk-of-bias appraisal requires human judgement and is not automated")
    else:
        start = 1
        rob_delta = 0
        rob_reason = ("no randomized / meta-analytic evidence — starts at observational-grade (Low) "
                      "certainty")
    domains.append(GradeDomain("risk of bias", rob_delta, rob_reason))

    # Inconsistency — the gate required directional agreement before deciding, so a decided
    # (non-Contested) verdict is, by construction, directionally consistent.
    domains.append(GradeDomain("inconsistency", 0,
                               "the deciding trial evidence is directionally consistent"))

    # Indirectness — the deciding set is filtered to on-population, on-outcome (non-surrogate).
    domains.append(GradeDomain("indirectness", 0,
                               "all deciding evidence is on the claimed population and measures the "
                               "claimed (non-surrogate) outcome"))

    # Imprecision (GRADE's precision domain — spans sample size, replication and effect size vs MID).
    imp_delta = 0
    reasons: list[str] = []
    single_sublarge = bool(rcts) and not metas and not large and len(rcts) < 2
    if single_sublarge:
        imp_delta -= 1
        reasons.append("rests on a single sub-large, unreplicated RCT")
    if not metas and not large and total_n and total_n < 500:
        imp_delta -= 1
        reasons.append(f"small total randomized sample (N={total_n})")
    if verdict is Verdict.SUPPORTED:
        from .magnitude import effect_strength, has_magnitude
        pros = [r for r in trials if r.supports]
        if has_magnitude(pros):
            strengths = {effect_strength(r) for r in pros}
            if "meaningful" not in strengths and "marginal" in strengths:
                imp_delta -= 1
                reasons.append("the supporting effect is statistically significant but sub-clinical "
                               "(below the minimal important difference)")
    if not reasons:
        reasons.append("adequately precise — meta-analytic and/or large or replicated randomized evidence")
    domains.append(GradeDomain("imprecision", imp_delta, "; ".join(reasons)))

    # Publication bias — cannot be assessed from structured fields alone; GRADE default is
    # "undetected" (no downgrade). Reported explicitly rather than silently skipped.
    domains.append(GradeDomain("publication bias", 0,
                               "not assessed (would require small-study / funnel analysis); no downgrade applied"))

    # Large-effect UPGRADE (GRADE): a dramatic all-or-none effect from NON-randomized evidence is
    # upgraded. When the same effect comes from a trial it already starts High, so no double-count.
    if dramatic and not randomized:
        domains.append(GradeDomain("large effect", 1,
                                   "an all-or-none / dramatic effect where the untreated course is "
                                   "uniformly poor (GRADE large-effect upgrade)"))

    return _assemble(start, domains)
