"""The deterministic core is testable with zero LLM calls — that's the point."""
from verdict.gates import EvidenceRow, Verdict, resolve


def _row(design, direction, pop=True, integrity=True):
    return EvidenceRow(citation="x", design=design, direction=direction,
                       population_match=pop, integrity_ok=integrity)


def test_supported_when_high_tier_agrees_positive():
    rows = [_row("meta-analysis of rcts", 1), _row("rct", 1)]
    assert resolve(rows)[0] is Verdict.SUPPORTED


def test_not_supported_on_null_high_tier():
    rows = [_row("meta-analysis of rcts", 0), _row("rct", 0)]
    assert resolve(rows)[0] is Verdict.NOT_SUPPORTED


def test_insufficient_when_only_preclinical():
    rows = [_row("preclinical", 1), _row("case report", 1)]
    assert resolve(rows)[0] is Verdict.INSUFFICIENT


def test_contested_on_high_tier_conflict():
    rows = [_row("rct", 1), _row("meta-analysis of rcts", -1)]
    assert resolve(rows)[0] is Verdict.CONTESTED


def test_integrity_excluded_rows_do_not_count():
    # A single fraudulent "positive" RCT must not flip an otherwise-empty base.
    rows = [_row("rct", 1, integrity=False)]
    assert resolve(rows)[0] is Verdict.INSUFFICIENT
