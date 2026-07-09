"""The definitive tier must let a NULL or LONE meta-analysis — the top evidence tier — temper a
positive signal, instead of stamping a confident Supported over it. Two real confident errors found
by the adversarial gate-hunt motivate this:
  - flibanserin: 3 positive pivotal RCTs but a decisive null meta-analysis (n≈5,914) -> Contested.
  - IVIG in sepsis: a lone positive pooled meta contradicted by a substantial null RCT -> Contested.
Both must land on Contested WITHOUT dragging down decisive evidence (a large replicated RCT, or a
huge meta only nicked by a tiny null trial).
"""
from verdict.gates import EvidenceRow, Verdict, resolve


def _row(design, direction, n_int, year=2015, pop=True, out=True):
    return EvidenceRow(citation="c", design=design, direction=direction, population_match=pop,
                       outcome_match=out, n_int=n_int, year=year)


# --- Fix A: a large NULL meta contests a LONE positive large RCT ---------------------------------
def test_large_null_meta_contests_a_lone_positive_large_rct():
    rows = [_row("rct", 1, 1080, 2013), _row("meta-analysis of rcts", 0, 5914, 2016)]
    verdict, _ = resolve(rows)
    assert verdict is Verdict.CONTESTED


def test_flibanserin_shape_is_contested_not_supported():
    rows = [
        _row("rct", 1, 1080, 2013), _row("rct", 1, 880, 2012), _row("rct", 1, 780, 2012),
        _row("meta-analysis of rcts", 0, 5914, 2016),
        _row("guideline / regulatory", 1, 0, 2015),
    ]
    verdict, _ = resolve(rows)
    assert verdict is Verdict.CONTESTED


def test_small_old_null_meta_does_not_contest_a_decisive_large_rct():
    """Regression guard: a large decisive RCT supersedes a tiny/old null meta -> stays Supported."""
    rows = [_row("rct", 1, 5000, 2020), _row("meta-analysis of rcts", 0, 200, 2005)]
    verdict, _ = resolve(rows)
    assert verdict is Verdict.SUPPORTED


def test_two_concordant_large_rcts_decide_over_a_null_meta():
    """Regression guard: replicated large RCTs remain decisive; a null meta doesn't contest them."""
    rows = [_row("rct", 1, 3000, 2019), _row("rct", 1, 2500, 2020), _row("meta-analysis of rcts", 0, 4000, 2018)]
    verdict, _ = resolve(rows)
    assert verdict is Verdict.SUPPORTED


# --- Fix B: a LONE positive meta contradicted by a substantial null RCT is Contested -------------
def test_lone_positive_meta_disputed_by_substantial_null_rct_is_contested():
    rows = [
        _row("meta-analysis of rcts", 1, 1430, 2007),
        _row("rct", 0, 653, 2007),
        _row("systematic review", 0, 1000, 2013),
    ]
    verdict, _ = resolve(rows)
    assert verdict is Verdict.CONTESTED


def test_lone_positive_meta_not_disputed_by_a_tiny_null_rct():
    """Regression guard: a huge meta is not overturned by a tiny (n<300) null pilot -> Supported."""
    rows = [_row("meta-analysis of rcts", 1, 50000, 2018), _row("rct", 0, 60, 2010)]
    verdict, _ = resolve(rows)
    assert verdict is Verdict.SUPPORTED


def test_lone_positive_meta_with_concordant_rct_stays_supported():
    """A lone meta that AGREES with its primary RCTs is not in conflict at all -> Supported."""
    rows = [_row("meta-analysis of rcts", 1, 1430, 2007), _row("rct", 1, 653, 2007)]
    verdict, _ = resolve(rows)
    assert verdict is Verdict.SUPPORTED
