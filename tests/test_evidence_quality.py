"""Evidence-quality cap: a verdict that rests on a single, unreplicated meta-analysis cannot
be High-certainty.

The engine reasons on study DESIGN TIER (meta > RCT > cohort) but cannot see the quality of
the trials pooled inside a meta. A lone meta with no corroborating large RCT is exactly where
pooling-of-junk hides — it is how, replaying history, the engine was High-certainty "Supported"
on ivermectin in 2021 off a positive meta built on trials later flagged. Replication (a second
concordant meta, or a large primary RCT, or >=2 primary RCTs) earns High; a lone synthesis does
not. This is certainty-only — it never changes a verdict.
"""
from verdict.certainty import grade_certainty
from verdict.corpora import load_rows
from verdict.gates import EvidenceRow, resolve
from verdict.timemachine import verdict_over_time


def _r(design, direction, n_int=0, year=2020):
    return EvidenceRow(citation="x", design=design, direction=direction, population_match=True,
                       outcome_match=True, n_int=n_int, year=year)


def test_lone_uncorroborated_meta_is_not_high():
    rows = [_r("meta-analysis of rcts", 1, n_int=1788), _r("rct", 1, n_int=180)]
    v = resolve(rows)[0]
    c = grade_certainty(rows, v)
    assert v.value == "Supported"          # the VERDICT is unchanged
    assert c.level == "Moderate"           # but no longer confidently High on a lone synthesis


def test_meta_corroborated_by_large_rct_is_high():
    rows = [_r("meta-analysis of rcts", 1, n_int=5000), _r("rct", 1, n_int=8000)]
    assert grade_certainty(rows, resolve(rows)[0]).level == "High"


def test_two_concordant_metas_is_high():
    rows = [_r("meta-analysis of rcts", 1, n_int=4000), _r("meta-analysis of rcts", 1, n_int=3000)]
    assert grade_certainty(rows, resolve(rows)[0]).level == "High"


def test_cap_surfaces_in_the_risk_of_bias_domain():
    rows = [_r("meta-analysis of rcts", 1, n_int=1788), _r("rct", 1, n_int=180)]
    c = grade_certainty(rows, resolve(rows)[0])
    rob = next(d for d in c.domains if d.name == "risk of bias")
    assert rob.delta == -1 and "meta" in rob.rationale.lower()


def test_ivermectin_2021_timepoint_no_longer_confidently_wrong():
    _, rows = load_rows("C08")
    tp = {t.year: t for t in verdict_over_time(rows)}
    assert tp[2021].verdict == "Supported"   # verdict at that time is unchanged
    assert tp[2021].certainty != "High"       # but it is no longer HIGH-certainty (the fix)


def test_cap_does_not_touch_a_single_rct_moderate():
    # a lone sub-large RCT (no meta) is already Moderate; the cap must not push it lower.
    rows = [_r("rct", 1, n_int=900)]
    assert grade_certainty(rows, resolve(rows)[0]).level == "Moderate"
