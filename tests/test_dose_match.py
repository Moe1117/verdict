"""Dose-directness: a trial that tested a DIFFERENT dose/regimen than the claim specifies is
INDIRECT for that dose-specific claim — exactly like a surrogate endpoint is indirect for the
outcome. So off-dose trials cannot establish efficacy at the claimed dose (the gabapentin-900mg
adversarial case: the positive trials used 1800-3600 mg). `dose_match` defaults True, so any claim
without a dose constraint — every existing corpus — behaves exactly as before (strict superset).
"""
from verdict.gates import EvidenceRow, Verdict, resolve


def _row(design, direction, n_int, dose_match=True, year=2015):
    return EvidenceRow(citation="c", design=design, direction=direction, population_match=True,
                       outcome_match=True, dose_match=dose_match, n_int=n_int, year=year)


def test_dose_match_defaults_true():
    """Strict superset: a row built without dose_match is on-dose by default — no behavior change."""
    r = EvidenceRow(citation="c", design="rct", direction=1, population_match=True, outcome_match=True, n_int=1500)
    assert r.dose_match is True


def test_off_dose_trials_are_indirect_and_abstain():
    """On-population, on-outcome, but OFF-DOSE positive trials -> no direct evidence at the claimed
    dose -> Insufficient, not a confident Supported (the gabapentin trap)."""
    rows = [_row("rct", 1, 1500, dose_match=False), _row("meta-analysis of rcts", 1, 5000, dose_match=False)]
    verdict, trace = resolve(rows)
    assert verdict is Verdict.INSUFFICIENT
    assert any("dose" in g.detail.lower() for g in trace)


def test_on_dose_trials_decide_normally():
    rows = [_row("meta-analysis of rcts", 1, 5000), _row("rct", 1, 1500)]
    verdict, _ = resolve(rows)
    assert verdict is Verdict.SUPPORTED


def test_off_dose_positive_is_excluded_leaving_the_on_dose_signal():
    """An off-dose positive RCT is dropped from the direct set; the on-dose null RCT decides."""
    rows = [_row("rct", 1, 1500, dose_match=False), _row("rct", 0, 1500, dose_match=True)]
    verdict, _ = resolve(rows)
    assert verdict is Verdict.NOT_SUPPORTED  # not Contested — the off-dose positive never counted


def test_surrogate_message_still_distinct_from_dose_message():
    """A surrogate-only failure keeps its own message (not conflated with off-dose)."""
    surrogate = EvidenceRow(citation="c", design="rct", direction=1, population_match=True,
                            outcome_match=False, dose_match=True, n_int=1500)
    verdict, trace = resolve([surrogate])
    assert verdict is Verdict.INSUFFICIENT
    assert any("surrogate" in g.detail.lower() for g in trace)
