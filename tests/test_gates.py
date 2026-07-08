"""The deterministic core is testable with zero LLM calls — that's the point.
These cases mirror the real demo claims (C08/C09/C01/C12/C05)."""
from verdict.gates import EvidenceRow, Verdict, resolve


def row(design, direction, pop=True, integrity=True, n_int=0, year=0, outcome=True, dramatic=False):
    return EvidenceRow(citation="x", design=design, direction=direction,
                       population_match=pop, integrity_ok=integrity, n_int=n_int, year=year,
                       outcome_match=outcome, dramatic_effect=dramatic)


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


def test_surrogate_only_is_insufficient():  # F02-like
    # On-population trials that measure only a surrogate cannot decide the outcome claim.
    rows = [row("meta-analysis of rcts", 0, outcome=False), row("rct", 1, n_int=400, outcome=False)]
    assert resolve(rows)[0] is Verdict.INSUFFICIENT


def test_supermajority_large_rcts_decide():  # M20-like (intensive BP)
    # Four positive large RCTs vs one older null must not read as Contested.
    rows = [
        row("rct", 1, n_int=4678), row("rct", 1, n_int=6414),
        row("rct", 1, n_int=5624), row("rct", 1, n_int=4243),
        row("rct", 0, n_int=2362),  # lone older null
    ]
    assert resolve(rows)[0] is Verdict.SUPPORTED


def test_all_or_none_fires_without_contradiction():  # N09/N13-like
    # A dramatic single-arm effect in a fatal disease, no randomized contradiction -> Supported.
    rows = [row("prospective cohort", 1, n_int=75, dramatic=True),
            row("prospective cohort", 1, n_int=79, dramatic=True)]
    v, trace = resolve(rows)
    assert v is Verdict.SUPPORTED and trace[-1].gate == "all-or-none"


def test_all_or_none_blocked_by_contradicting_rct():  # bevacizumab/glioblastoma negative control
    # A dramatic single-arm positive that phase-3 RCTs contradict must NOT fire the path.
    rows = [
        row("prospective cohort", 1, n_int=60, dramatic=True),
        row("rct", 0, n_int=458), row("rct", 0, n_int=637),
    ]
    assert resolve(rows)[0] is Verdict.NOT_SUPPORTED
