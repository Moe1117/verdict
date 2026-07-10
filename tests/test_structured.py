# tests/test_structured.py
from verdict.trialmatch import PatientProfile, Criterion, eval_structured

def _crit(field, op, lo=None, hi=None, kind="inclusion"):
    return Criterion(id="c", kind=kind, ctype="structured", predicate="p",
                     source_text="s", field=field, op=op, lo=lo, hi=hi)

def test_age_in_range_is_met():
    p = PatientProfile(age=62, age_src="62-year-old")
    res, phrase, _ = eval_structured(_crit("age", "range", 18, 75), p)
    assert res == "MET" and phrase == "62-year-old"

def test_age_out_of_range_is_not_met():
    p = PatientProfile(age=80, age_src="80yo")
    res, _, _ = eval_structured(_crit("age", "range", 18, 75), p)
    assert res == "NOT_MET"

def test_missing_field_is_insufficient():
    p = PatientProfile()  # no age
    res, phrase, _ = eval_structured(_crit("age", "range", 18, 75), p)
    assert res == "INSUFFICIENT" and phrase == "not stated"

def test_ecog_max_is_met():
    p = PatientProfile(ecog=1, ecog_src="ECOG 1")
    res, _, _ = eval_structured(_crit("ecog", "range", 0, 1), p)
    assert res == "MET"

def test_lab_min_threshold():
    p = PatientProfile(labs={"ANC": 1.8})
    res, _, _ = eval_structured(_crit("ANC", "min", lo=1.5), p)
    assert res == "MET"
    res2, _, _ = eval_structured(_crit("ANC", "min", lo=2.0), p)
    assert res2 == "NOT_MET"
