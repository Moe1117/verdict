"""The deterministic core is testable with zero LLM calls — that's the point.
These cases mirror the real demo claims (C08/C09/C01/C12/C05)."""
from verdict.gates import EvidenceRow, Verdict, resolve


def row(design, direction, pop=True, integrity=True, n_int=0, year=0):
    return EvidenceRow(citation="x", design=design, direction=direction,
                       population_match=pop, integrity_ok=integrity, n_int=n_int, year=year)


def test_supported_when_trials_agree_positive():  # C01-like
    assert resolve([row("meta-analysis of rcts", 1), row("rct", 1)])[0] is Verdict.SUPPORTED


def test_not_supported_on_null_trials():
    assert resolve([row("meta-analysis of rcts", 0), row("rct", 0)])[0] is Verdict.NOT_SUPPORTED


def test_insufficient_when_no_trial_evidence():  # C09-like
    # A narrative review + case reports + preclinical is NOT trial evidence.
    rows = [row("systematic review", 0), row("case report", -1), row("preclinical", 1, pop=False)]
    assert resolve(rows)[0] is Verdict.INSUFFICIENT


def test_lone_review_is_not_trial_evidence():
    assert resolve([row("systematic review", 1)])[0] is Verdict.INSUFFICIENT


def test_integrity_excluded_row_does_not_count():
    # A retracted "positive" RCT must not survive to flip an otherwise-null base.
    rows = [row("rct", 1, integrity=False, n_int=600), row("meta-analysis of rcts", 0)]
    assert resolve(rows)[0] is Verdict.NOT_SUPPORTED


def test_large_rcts_dominate_conflict():  # C08-like
    rows = [
        row("rct", -1, n_int=3515), row("rct", -1, n_int=8811),   # TOGETHER / PRINCIPLE
        row("meta-analysis of rcts", 1, year=2021),               # old positive meta
        row("rct", 1, n_int=180),                                 # small positive RCT
    ]
    assert resolve(rows)[0] is Verdict.NOT_SUPPORTED


def test_recent_metas_conflict_is_contested():  # C12-like
    rows = [
        row("meta-analysis of rcts", 0, year=2025), row("meta-analysis of rcts", 1, year=2026),
        row("rct", 1, n_int=40), row("rct", 1, n_int=80),
    ]
    assert resolve(rows)[0] is Verdict.CONTESTED


def test_observational_reviews_do_not_override_null_trials():  # C05-like
    rows = [
        row("target-trial emulation", 0), row("meta-analysis of rcts", 0),
        row("systematic review", 1), row("systematic review", 1),   # observational reviews, excluded
    ]
    assert resolve(rows)[0] is Verdict.NOT_SUPPORTED
