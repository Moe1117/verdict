"""Verdict over time — replay a claim as its evidence accrued, year by year.

Purely additive: it reuses resolve() on time-filtered rows, so it can never change a
verdict. The final timepoint must equal the full current verdict.
"""
from verdict.corpora import load_rows
from verdict.gates import EvidenceRow, resolve
from verdict.timemachine import Timepoint, verdict_over_time


def _row(design, direction, year, n_int=0, pop=True, integrity=True, outcome=True):
    return EvidenceRow(citation="x", design=design, direction=direction, population_match=pop,
                       year=year, n_int=n_int, integrity_ok=integrity, outcome_match=outcome)


def test_timepoints_are_sorted_and_cumulative():
    rows = [_row("rct", 1, 2022, n_int=6000), _row("rct", 0, 2020, n_int=5000)]
    tl = verdict_over_time(rows)
    assert [t.year for t in tl] == [2020, 2022]         # sorted ascending
    assert [t.n_studies for t in tl] == [1, 2]          # cumulative


def test_final_timepoint_matches_resolve_over_dated_evidence():
    """The last timepoint equals the verdict over all DATED evidence — the module's actual
    contract (undated rows are not placed on the timeline). For a fully-dated corpus that also
    equals the current verdict over ALL rows."""
    _, rows = load_rows("C08")
    dated = [r for r in rows if r.year and r.year > 0]
    assert verdict_over_time(rows)[-1].verdict == resolve(dated)[0].value
    assert resolve(dated)[0].value == resolve(rows)[0].value   # C08 is fully dated


def test_final_timepoint_is_dated_resolve_even_when_undated_rows_would_change_it():
    """Precision guard for the finding: undated verdict-changing rows are intentionally NOT on
    the timeline, so the final timepoint tracks resolve(dated), not resolve(all)."""
    rows = [_row("rct", 1, 2020, n_int=100),        # dated, thin -> Insufficient alone
            _row("rct", 1, 0, n_int=9000), _row("rct", 1, 0, n_int=9000)]  # undated, would decide
    dated = [r for r in rows if r.year and r.year > 0]
    assert verdict_over_time(rows)[-1].verdict == resolve(dated)[0].value


def test_ivermectin_arc_turns():
    """The hero trajectory: the science visibly turns as clean RCTs arrive."""
    _, rows = load_rows("C08")
    arc = {t.year: t.verdict for t in verdict_over_time(rows)}
    assert arc[2020] == "Insufficient"
    assert arc[2021] == "Supported"
    assert arc[2022] == "Contested"
    assert arc[2024] == "Not Supported"


def test_changed_flag_marks_turns():
    tl = verdict_over_time([_row("meta-analysis of rcts", 1, 2020),
                            _row("rct", 0, 2021, n_int=9000)])
    assert tl[0].changed is True                          # first state is a change from nothing
    assert isinstance(tl[0], Timepoint)


def test_undated_rows_are_excluded_but_engine_still_safe():
    # a row with no year cannot be placed on the timeline; it must not crash the sweep.
    rows = [_row("rct", 1, 2020, n_int=5000), _row("rct", 1, 0, n_int=9000)]
    tl = verdict_over_time(rows)
    assert [t.year for t in tl] == [2020]


def test_carries_certainty_level():
    _, rows = load_rows("M07")
    tl = verdict_over_time(rows)
    assert tl and all(t.certainty in ("Very Low", "Low", "Moderate", "High") for t in tl)
