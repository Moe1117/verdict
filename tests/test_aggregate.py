# tests/test_aggregate.py
from verdict.trialmatch import CriterionResult, aggregate

def _r(kind, result):
    return CriterionResult(id="x", kind=kind, result=result, confidence="high",
                           evidence_phrase="", note="", predicate="", source_text="")

def test_exclusion_met_is_ineligible():
    assert aggregate([_r("inclusion", "MET"), _r("exclusion", "MET")]) == "Ineligible"

def test_inclusion_not_met_is_ineligible():
    assert aggregate([_r("inclusion", "NOT_MET"), _r("exclusion", "NOT_MET")]) == "Ineligible"

def test_all_inclusions_met_no_exclusions_fire_is_likely_eligible():
    assert aggregate([_r("inclusion", "MET"), _r("inclusion", "MET"),
                      _r("exclusion", "NOT_MET")]) == "Likely eligible"

def test_any_insufficient_without_definitive_fail_is_needs_verification():
    assert aggregate([_r("inclusion", "MET"), _r("inclusion", "INSUFFICIENT"),
                      _r("exclusion", "NOT_MET")]) == "Needs verification"

def test_exclusion_insufficient_is_needs_verification():
    assert aggregate([_r("inclusion", "MET"), _r("exclusion", "INSUFFICIENT")]) == "Needs verification"

def test_definitive_fail_beats_insufficient():
    # a NOT_MET inclusion is disqualifying even if another criterion is unresolved
    assert aggregate([_r("inclusion", "NOT_MET"), _r("inclusion", "INSUFFICIENT")]) == "Ineligible"

def test_empty_is_needs_verification():
    assert aggregate([]) == "Needs verification"
