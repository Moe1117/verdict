"""The effect-magnitude classifier is deterministic and testable with synthetic rows."""
from verdict.gates import EvidenceRow
from verdict.magnitude import effect_strength, has_magnitude


def r(**kw):
    base = dict(citation="x", design="rct", direction=1, population_match=True)
    base.update(kw)
    return EvidenceRow(**base)


def test_meaningful_ratio_effect():
    assert effect_strength(r(sig="significant", effect_point=0.75, effect_scale="ratio")) == "meaningful"


def test_marginal_ratio_effect():
    # significant but sub-10% relative effect -> marginal (cannot become a confident yes)
    assert effect_strength(r(sig="significant", effect_point=0.96, effect_scale="ratio")) == "marginal"


def test_nonsignificant_is_null():
    assert effect_strength(r(sig="nonsignificant", effect_point=0.85, effect_scale="ratio")) == "null"


def test_missing_magnitude_is_unknown():
    assert effect_strength(r()) == "unknown"  # no sig/effect -> falls back to sign-only logic


def test_has_magnitude_gate():
    assert not has_magnitude([r(), r()])
    assert has_magnitude([r(), r(sig="significant", effect_point=0.7, effect_scale="ratio")])
