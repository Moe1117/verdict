"""The per-domain GRADE certainty profile.

Every verdict carries an auditable breakdown across the GRADE domains
(risk of bias / inconsistency / indirectness / imprecision / publication bias,
plus a large-effect upgrade), each with an explicit ±delta and a rationale.

The refactor is BEHAVIOR-PRESERVING: the certainty SCORE it produces is identical
to the prior logic for every possible evidence set, so the empirically-validated
calibration (which buckets by certainty level) cannot move. The first two tests
prove that against a frozen copy of the legacy scorer over thousands of random
row-sets; the rest pin the profile's structure and arithmetic.
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from verdict.certainty import CORE_DOMAINS, GradeDomain, grade_certainty
from verdict.gates import DESIGN_WEIGHT, EvidenceRow, Verdict, resolve
from verdict.magnitude import effect_strength, has_magnitude

LARGE_RCT_N = 1000


# ---- frozen legacy oracle: the certainty scoring BEFORE the profile refactor ----
def _legacy_score(rows, verdict):
    if verdict is Verdict.INSUFFICIENT:
        return 0
    if verdict is Verdict.CONTESTED:
        return 1
    deciding = [r for r in rows if r.integrity_ok and r.population_match and r.outcome_match]
    trials = [r for r in deciding if r.is_trial]
    metas = [r for r in trials if r.is_meta]
    rcts = [r for r in trials if r.is_rct]
    large = [r for r in rcts if r.n_int >= LARGE_RCT_N]
    dramatic = [r for r in deciding if r.dramatic_effect]
    total_n = sum(r.n_int for r in trials if r.n_int)
    if metas:
        score = 3
    elif large or len(rcts) >= 2:
        score = 3
    elif rcts:
        score = 2
    elif dramatic:
        score = 2
    else:
        score = 1
    # Evidence-quality cap: a lone, unreplicated meta cannot be High-certainty.
    if len(metas) == 1 and not large and len(rcts) < 2:
        score -= 1
    if not metas and not large and total_n and total_n < 500:
        score -= 1
    if verdict is Verdict.SUPPORTED:
        pros = [r for r in trials if r.supports]
        if has_magnitude(pros):
            strengths = {effect_strength(r) for r in pros}
            if "meaningful" not in strengths and "marginal" in strengths:
                score -= 1
    return max(0, min(3, score))


_DESIGNS = list(DESIGN_WEIGHT)
_rows = st.lists(
    st.builds(
        EvidenceRow,
        citation=st.just("x"),
        design=st.sampled_from(_DESIGNS),
        direction=st.sampled_from([-1, 0, 1]),
        population_match=st.booleans(),
        outcome_match=st.booleans(),
        dramatic_effect=st.booleans(),
        integrity_ok=st.booleans(),
        n_int=st.integers(min_value=0, max_value=50000),
        year=st.integers(min_value=1990, max_value=2026),
    ),
    max_size=8,
)


@given(_rows)
@settings(max_examples=1500)
def test_profile_score_equals_legacy(rows):
    """The refactor cannot move ANY certainty score -> calibration is untouched."""
    v = resolve(rows)[0]
    assert grade_certainty(rows, v).score == _legacy_score(rows, v)


# Also cover magnitude-bearing rows (ratio effects), which the legacy scorer reads.
_mag_rows = st.lists(
    st.builds(
        EvidenceRow,
        citation=st.just("x"),
        design=st.sampled_from(["rct", "meta-analysis of rcts"]),
        direction=st.sampled_from([-1, 0, 1]),
        population_match=st.just(True),
        outcome_match=st.just(True),
        integrity_ok=st.just(True),
        n_int=st.integers(min_value=0, max_value=5000),
        effect_point=st.floats(min_value=0.5, max_value=2.0),
        effect_scale=st.just("ratio"),
        sig=st.sampled_from(["significant", "nonsignificant", "not_reported"]),
    ),
    min_size=1,
    max_size=5,
)


@given(_mag_rows)
@settings(max_examples=800)
def test_profile_score_equals_legacy_with_magnitude(rows):
    v = resolve(rows)[0]
    assert grade_certainty(rows, v).score == _legacy_score(rows, v)


def _row(design, direction, n_int=0, pop=True, integrity=True, dramatic=False, outcome=True):
    return EvidenceRow(citation="x", design=design, direction=direction, population_match=pop,
                       n_int=n_int, integrity_ok=integrity, dramatic_effect=dramatic, outcome_match=outcome)


def test_all_four_verdict_types_carry_five_core_domains():
    """A full GRADE profile — all five core domains, each explained — on every verdict."""
    cases = {
        "supported": [_row("meta-analysis of rcts", 1), _row("rct", 1, n_int=8000)],
        "not_supported": [_row("meta-analysis of rcts", 0), _row("rct", 0, n_int=8000)],
        "contested": [_row("rct", 1, n_int=8000), _row("rct", 0, n_int=9000)],
        "insufficient": [],
    }
    for label, rows in cases.items():
        v = resolve(rows)[0]
        c = grade_certainty(rows, v)
        names = [d.name for d in c.domains]
        assert len(names) == len(set(names)), f"{label}: duplicate domain"
        for dom in CORE_DOMAINS:
            assert dom in names, f"{label} missing GRADE domain: {dom}"
        assert all(isinstance(d, GradeDomain) and d.rationale.strip() for d in c.domains)


def test_profile_arithmetic_reconciles_to_score():
    """start tier + the sum of domain deltas == the final score (clamped)."""
    for rows in (
        [_row("meta-analysis of rcts", 1), _row("rct", 1, n_int=8000)],
        [_row("rct", 1, n_int=900)],
        [_row("rct", 1, n_int=200)],
        [_row("rct", 1, n_int=8000), _row("rct", 0, n_int=9000)],  # contested
        [],  # insufficient
    ):
        v = resolve(rows)[0]
        c = grade_certainty(rows, v)
        assert c.score == max(0, min(3, c.start + sum(d.delta for d in c.domains)))


def test_single_sublarge_rct_downgrades_imprecision():
    rows = [_row("rct", 1, n_int=900)]
    c = grade_certainty(rows, resolve(rows)[0])
    imp = next(d for d in c.domains if d.name == "imprecision")
    assert imp.delta == -1
    assert c.level == "Moderate"


def test_high_certainty_body_has_no_downgrades():
    rows = [_row("meta-analysis of rcts", 1), _row("rct", 1, n_int=8000)]
    c = grade_certainty(rows, resolve(rows)[0])
    assert c.level == "High"
    assert all(d.delta == 0 for d in c.domains)  # nothing dragged it below the RCT-grade start


def test_contested_is_a_serious_inconsistency_downgrade():
    rows = [_row("rct", 1, n_int=8000), _row("rct", 0, n_int=9000)]
    assert resolve(rows)[0] is Verdict.CONTESTED
    c = grade_certainty(rows, Verdict.CONTESTED)
    inc = next(d for d in c.domains if d.name == "inconsistency")
    assert inc.delta < 0
    assert c.level == "Low"


def test_signals_backward_compatible():
    """export_cards.py + the web still read `.signals`; it stays a non-empty list of str."""
    rows = [_row("rct", 1, n_int=900)]
    c = grade_certainty(rows, resolve(rows)[0])
    assert isinstance(c.signals, list) and c.signals
    assert all(isinstance(s, str) and s for s in c.signals)
