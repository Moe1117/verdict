"""Certainty, calibration, and robustness are deterministic — testable with no LLM."""
from verdict.calibrate import fit, risk_coverage, wilson
from verdict.certainty import grade_certainty
from verdict.gates import EvidenceRow, Verdict, resolve
from verdict.robustness import robustness


def row(design, direction, n_int=0, pop=True, integrity=True, dramatic=False):
    return EvidenceRow(citation="x", design=design, direction=direction, population_match=pop,
                       n_int=n_int, integrity_ok=integrity, dramatic_effect=dramatic)


def test_certainty_high_from_metas():
    rows = [row("meta-analysis of rcts", 1), row("rct", 1, n_int=8000)]
    v = resolve(rows)[0]
    assert grade_certainty(rows, v).level == "High"


def test_certainty_moderate_single_small_rct():
    rows = [row("rct", 1, n_int=900)]
    assert grade_certainty(rows, resolve(rows)[0]).level == "Moderate"


def test_certainty_contested_is_low_insufficient_is_very_low():
    contested = [row("rct", 1, n_int=8000), row("rct", 0, n_int=9000)]
    assert resolve(contested)[0] is Verdict.CONTESTED
    assert grade_certainty(contested, Verdict.CONTESTED).level == "Low"
    assert grade_certainty([], Verdict.INSUFFICIENT).level == "Very Low"


def test_wilson_bounds_sane():
    lo, hi = wilson(9, 10)
    assert 0.0 <= lo < 0.9 < hi <= 1.0


def test_calibration_abstains_on_thin_bucket():
    cal = fit([("High", True)] * 6 + [("Low", True)] * 2)  # Low has n=2 < MIN_SUPPORT
    assert cal.buckets["High"].accuracy == 1.0
    assert cal.confidence_for("Low") == "insufficient calibration data"


def test_risk_coverage_monotone_coverage():
    scored = [(3, True), (3, True), (2, True), (1, False), (0, False)]
    rc = risk_coverage(scored)
    covs = [r["coverage"] for r in rc]
    assert covs == sorted(covs, reverse=True)  # coverage falls as the threshold rises


def test_robustness_flags_single_study_dependence():
    # Verdict rests on one large RCT; dropping it changes the call -> not robust.
    rows = [row("rct", 1, n_int=8000)]
    r = robustness(rows)
    assert r.stability == 0.0 and r.survives_drop_largest is False
