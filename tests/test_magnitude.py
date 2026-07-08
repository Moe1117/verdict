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


def test_precise_null_vs_wide_null():
    # tight CI around 1.0 rules out a meaningful effect -> genuine no-effect (a real contradiction)
    assert effect_strength(r(sig="nonsignificant", effect_point=0.99, ci_low=0.90, ci_high=1.09,
                             effect_scale="ratio")) == "precise_null"
    # CI still admits a meaningful benefit (0.80) -> absence of signal, not counter-evidence
    assert effect_strength(r(sig="nonsignificant", effect_point=0.92, ci_low=0.80, ci_high=1.06,
                             effect_scale="ratio")) == "wide_null"


def test_missing_magnitude_is_unknown():
    assert effect_strength(r()) == "unknown"  # no sig/effect -> falls back to sign-only logic


def test_has_magnitude_gate():
    assert not has_magnitude([r(), r()])
    assert has_magnitude([r(), r(sig="significant", effect_point=0.7, effect_scale="ratio")])


def test_magnitude_changes_certainty_not_verdict():
    from verdict.certainty import grade_certainty
    from verdict.gates import resolve
    meaningful = [r(design="rct", direction=1, n_int=5000, sig="significant", effect_point=0.70, effect_scale="ratio")]
    marginal = [r(design="rct", direction=1, n_int=5000, sig="significant", effect_point=0.97, effect_scale="ratio")]
    vm, vg = resolve(meaningful)[0], resolve(marginal)[0]
    assert vm.value == vg.value == "Supported"  # the verdict is identical — magnitude never moves it
    # ...but a marginal (sub-clinical) supporting effect is less certain than a meaningful one
    assert grade_certainty(marginal, vg).score < grade_certainty(meaningful, vm).score
