# tests/test_trialcard.py
from verdict.trialmatch import PatientProfile, Criterion, CriterionResult, TrialCard

def test_models_construct_with_sensible_defaults():
    p = PatientProfile(age=62, sex="FEMALE", raw_note="62F ...")
    assert p.age == 62 and p.biomarkers == [] and p.labs == {}
    c = Criterion(id="inc1", kind="inclusion", ctype="structured",
                  predicate="Aged 18-75", source_text="Aged 18-75 (inclusive) years old",
                  field="age", op="range", lo=18, hi=75)
    assert c.kind == "inclusion" and c.hi == 75
    r = CriterionResult(id="inc1", kind="inclusion", result="MET", confidence="high",
                        evidence_phrase="62-year-old", note="18<=62<=75",
                        predicate=c.predicate, source_text=c.source_text)
    assert r.result == "MET"
    card = TrialCard(nct_id="NCT06927986", title="t", status="RECRUITING",
                     url="u", verdict="Needs verification", criteria=[r],
                     to_verify=["confirm labs"], n_met=1, n_disqualifying=0, n_to_verify=1)
    assert card.verdict == "Needs verification" and card.criteria[0].id == "inc1"
