"""Property-based proof of the safety invariants that back 'never confidently wrong'.

These hold for ARBITRARY evidence, not just the benchmark: Hypothesis generates
thousands of random row-sets and asserts the engine can never (1) be swayed by a
retracted study, (2) assert Supported without a genuine on-population, on-outcome
supporter, or (3) assert Supported when every on-outcome study is null/against.
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from verdict.gates import DESIGN_WEIGHT, EvidenceRow, Verdict, resolve

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


def _supporter(rows):
    return any(r.integrity_ok and r.population_match and r.outcome_match and r.direction == 1 for r in rows)


@given(_rows)
@settings(max_examples=400)
def test_retracted_rows_are_inert(rows):
    """Adding a retracted (integrity_ok=False) study can never change the verdict."""
    retracted = EvidenceRow(citation="r", design="rct", direction=1, population_match=True,
                            outcome_match=True, integrity_ok=False, n_int=9999, year=2020)
    assert resolve(rows)[0] is resolve(rows + [retracted])[0]


@given(_rows)
@settings(max_examples=1000)
def test_supported_requires_a_genuine_supporter(rows):
    """The engine NEVER returns Supported without >=1 integrity-ok, on-population,
    on-outcome study that actually supports the claim. It cannot manufacture a 'yes'."""
    if resolve(rows)[0] is Verdict.SUPPORTED:
        assert _supporter(rows)


@given(_rows)
@settings(max_examples=1000)
def test_no_supporter_never_supported(rows):
    """Contrapositive: if nothing genuinely supports the claim, the verdict is never Supported
    — the structural core of 'never confidently wrong'."""
    if not _supporter(rows):
        assert resolve(rows)[0] is not Verdict.SUPPORTED
