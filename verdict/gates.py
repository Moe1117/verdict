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
    "guideline / regulatory": 2,  # guideline / FDA action / expert perspective — context, not a trial

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
    outcome_match: bool = True    # does the endpoint measure the CLAIMED outcome? False = surrogate / off-target
    dose_match: bool = True        # did the study test the CLAIMED dose/regimen? False = off-dose (indirect)
    dramatic_effect: bool = False # all-or-none / very-large effect on the claimed outcome where the untreated
                                  # course is uniformly poor (GRADE large-effect; Oxford CEBM all-or-none) —
                                  # decision-grade even from single-arm or a single pivotal trial
    integrity_ok: bool = True     # False when a citable retraction/EoC applies (see integrity.py)
    n: str = ""                   # sample size (display)
    n_int: int = 0                # sample size (numeric, for the large-RCT rule)
    year: int = 0                 # publication year (numeric, for recency)
    finding: str = ""             # one-line finding (display; our words, no verbatim abstract)
    integrity_note: str = ""      # why integrity_ok is False, with a citable source
    note: str = ""
    # Optional structured magnitude / precision — promoted from the finding prose where the
    # extractor reports it. All default to "unknown" so a row without them behaves exactly as a
    # pure-direction row (strict superset — no gate reads these unless populated).
    effect_point: float | None = None   # HR / RR / OR / mean-diff point estimate
    ci_low: float | None = None         # lower 95% CI bound
    ci_high: float | None = None        # upper 95% CI bound
    effect_scale: str = ""              # ratio | mean_diff | proportion_diff
    sig: str = ""                       # significant | nonsignificant | not_reported
    is_primary: bool | None = None      # measured the trial's PRIMARY (vs secondary) endpoint

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

    # Gate 0b — all-or-none / dramatic effect (GRADE large-effect; Oxford CEBM all-or-none).
    # A dramatic, directionally-consistent effect on the claimed outcome — a single-arm
    # response where the untreated course is uniformly poor (CAR-T in refractory leukaemia),
    # or a single pivotal trial stopped early for a near all-or-none benefit (nusinersen in
    # infantile SMA) — is decision-grade even without replication or a control arm, UNLESS a
    # randomized / meta-analytic study contradicts it (then the higher grade decides below).
    onpop_out = [r for r in rows if r.population_match and r.outcome_match and r.dose_match]
    dramatic = [r for r in onpop_out if r.dramatic_effect]
    if dramatic:
        if all(r.supports for r in dramatic) and not any(r.is_trial and r.against for r in onpop_out):
            trace.append(GateTrace("all-or-none", True,
                                   f"{len(dramatic)} study(ies) show an all-or-none / dramatic effect; "
                                   "no randomized evidence contradicts"))
            return Verdict.SUPPORTED, trace
        if all(r.against for r in dramatic) and not any(r.is_trial and r.supports for r in onpop_out):
            trace.append(GateTrace("all-or-none", True,
                                   f"{len(dramatic)} study(ies) show a dramatic absence of effect; "
                                   "no randomized evidence contradicts"))
            return Verdict.NOT_SUPPORTED, trace

    # Gate 1 — trial-grade human evidence on-population AND on the claimed outcome.
    on_pop = [r for r in rows if r.is_trial and r.population_match]
    if not on_pop:
        trace.append(GateTrace("direct-evidence", False,
                               "no on-population randomized/meta evidence — absence of evidence"))
        return Verdict.INSUFFICIENT, trace
    # Outcome-directness (GRADE): a trial that measures only a SURROGATE / off-target
    # endpoint is indirect — it cannot decide a claim about the actual clinical outcome.
    on_outcome = [r for r in on_pop if r.outcome_match]
    if not on_outcome:
        trace.append(GateTrace("direct-evidence", False,
                               "on-population trials measure only surrogate / off-target endpoints — "
                               "no direct evidence on the claimed outcome"))
        return Verdict.INSUFFICIENT, trace
    # Dose-directness: a trial that tested a DIFFERENT dose/regimen than the claim specifies is
    # indirect for that dose — it cannot establish efficacy at the claimed dose.
    trials = [r for r in on_outcome if r.dose_match]
    if not trials:
        trace.append(GateTrace("direct-evidence", False,
                               "on-population trials tested a different dose/regimen than the claim "
                               "specifies — no direct evidence at the claimed dose"))
        return Verdict.INSUFFICIENT, trace
    trace.append(GateTrace("direct-evidence", True,
                           f"{len(trials)} trial-grade on-population study(ies) on the claimed outcome"))

    # Gate 1b — sufficiency: a single small trial (no meta, no target-trial, no
    # large or replicated RCT) is too thin to conclude. Abstain rather than decide.
    strong = [r for r in trials if r.is_meta or r.design.strip().lower() == "target-trial emulation"]
    rcts = [r for r in trials if r.is_rct]
    largest_rct = max((r.n_int for r in rcts), default=0)
    if not strong and len(rcts) < 2 and largest_rct < 300:
        trace.append(GateTrace("sufficiency", False,
                               "only a single small trial on-population — too thin to conclude"))
        return Verdict.INSUFFICIENT, trace
    trace.append(GateTrace("sufficiency", True, "trial evidence adequate to assess"))

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

    # Gate 3 — trial evidence conflicts: let the definitive tier decide, but only
    # when that tier is itself coherent. EBM-hierarchy discipline: a single primary
    # study never overturns a meta-of-RCTs pointing the other way; a thin/older
    # synthesis never manufactures a consensus over directly-conflicting evidence.
    metas_all = [r for r in trials if r.is_meta]
    large = [r for r in trials if r.is_rct and r.n_int >= LARGE_RCT_N]
    if large:
        lpro = [r for r in large if r.supports]
        lcon = [r for r in large if r.against]
        # Large RCTs disagree among themselves. A clear SUPERMAJORITY (>=3 and >=3x
        # the dissent) still decides — a lone older/underpowered null does not make
        # replicated agreement "contested". A genuine split (e.g. 1-vs-1) is Contested.
        if lpro and lcon:
            if len(lpro) >= 3 and len(lpro) >= 3 * len(lcon):
                trace.append(GateTrace("definitive-evidence", True,
                                       f"{len(lpro)} large RCTs show the effect vs {len(lcon)} null — replicated majority"))
                return Verdict.SUPPORTED, trace
            if len(lcon) >= 3 and len(lcon) >= 3 * len(lpro):
                trace.append(GateTrace("definitive-evidence", True,
                                       f"{len(lcon)} large RCTs show no effect vs {len(lpro)} positive — replicated majority"))
                return Verdict.NOT_SUPPORTED, trace
            trace.append(GateTrace("definitive-evidence", False, "large RCTs themselves conflict"))
            return Verdict.CONTESTED, trace
        large_dir = -1 if lcon else 1
        largest_large_n = max((r.n_int for r in large), default=0)
        has_supporting_meta = any(m.supports for m in metas_all)
        # A lone (unreplicated) large RCT does NOT overturn a meta-of-RCTs that conflicts with it:
        # an actively-opposite meta (randomized synthesis outranks one trial), OR a NULL meta the RCT
        # does not supersede WHEN no meta actually supports the effect — a meta-analysis that pooled
        # at least as many patients and found no effect, with no corroborating positive synthesis, is
        # decision-grade counter-evidence. Two+ concordant large RCTs remain decisive (replication);
        # a small/old null meta a large RCT dwarfs, or a null meta counterbalanced by a positive one,
        # does not contest it.
        if len(large) < 2 and any(
            (large_dir == 1 and (m.direction == -1 or
                                 (m.direction == 0 and m.n_int >= largest_large_n and not has_supporting_meta)))
            or (large_dir == -1 and m.direction == 1)
            for m in metas_all
        ):
            trace.append(GateTrace("definitive-evidence", False,
                                   "a single large RCT conflicts with a meta-analysis of RCTs"))
            return Verdict.CONTESTED, trace
        if large_dir == -1:
            trace.append(GateTrace("definitive-evidence", True,
                                   f"{len(large)} large RCT(s) show no effect; positive signal is smaller/older"))
            return Verdict.NOT_SUPPORTED, trace
        trace.append(GateTrace("definitive-evidence", True, f"{len(large)} large RCT(s) show the effect"))
        return Verdict.SUPPORTED, trace

    metas = [r for r in trials if r.is_meta and r.year]
    if metas:
        newest = max(r.year for r in metas)
        recent = [r for r in metas if r.year >= newest - RECENT_META_WINDOW]
        older = [r for r in metas if r.year < newest - RECENT_META_WINDOW]
        rcts_onpop = [r for r in trials if r.is_rct]
        if all(r.against for r in recent):
            max_recent_n = max((r.n_int for r in recent), default=0)
            # Symmetric to the positive guard below: a recent null/negative meta
            # refutes only if it is not contradicted by a substantial OLDER positive
            # meta it fails to supersede (>=10x its sample). A lone recent null over
            # a genuinely split meta body is manufactured consensus -> Contested.
            unsuperseded_pos = any(
                not (max_recent_n >= 10 * max(o.n_int, 1)) for o in older if o.supports
            )
            if unsuperseded_pos:
                trace.append(GateTrace("definitive-evidence", False,
                                       "recent null rests against an unsuperseded older positive synthesis"))
                return Verdict.CONTESTED, trace
            trace.append(GateTrace("definitive-evidence", True, "recent meta-analyses agree: no effect"))
            return Verdict.NOT_SUPPORTED, trace
        if all(r.supports for r in recent):
            max_recent_n = max((r.n_int for r in recent), default=0)
            # A recent POSITIVE meta does not establish an effect if a far-larger
            # OLDER meta found no effect, or if it carries no poolable RCT sample
            # (n_int == 0, a network/narrative pooling) while on-population primary
            # RCTs directly contradict it.
            superseded = any(o.against and o.n_int >= 10 * max(max_recent_n, 1) for o in older)
            no_pool_conflict = max_recent_n == 0 and any(r.direction in (-1, 0) for r in rcts_onpop)
            # Pooling-of-junk trap: a LONE positive meta (the ONLY synthesis, no corroborating large
            # RCT) whose pooled result is contradicted by a SUBSTANTIAL on-population primary RCT
            # (n>=300, not a pilot) has unverified quality and is directly disputed — it cannot
            # confidently decide. A huge meta a tiny null trial merely nicks still stands.
            lone_meta_disputed = len(metas_all) == 1 and any(
                r.against and r.n_int >= 300 for r in rcts_onpop)
            if superseded or no_pool_conflict or lone_meta_disputed:
                trace.append(GateTrace("definitive-evidence", False,
                                       "positive signal rests on thin/superseded synthesis vs conflicting evidence"))
                return Verdict.CONTESTED, trace
            trace.append(GateTrace("definitive-evidence", True, "recent meta-analyses agree: effect present"))
            return Verdict.SUPPORTED, trace
        trace.append(GateTrace("definitive-evidence", False,
                               "recent high-quality evidence genuinely conflicts"))
        return Verdict.CONTESTED, trace

    trace.append(GateTrace("consistency", False, "trial evidence conflicts with no dominant tier"))
    return Verdict.CONTESTED, trace
