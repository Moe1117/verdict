from verdict import trialmatch as tm
from verdict.trialmatch import Criterion, PatientProfile


def test_match_builds_card_and_verify_list(monkeypatch):
    p = PatientProfile(age=62, age_src="62yo", ecog=1, ecog_src="ECOG 1")
    crits = [
        Criterion("inc1", "inclusion", "structured", "Aged 18-75", "Aged 18-75",
                  field="age", op="range", lo=18, hi=75),
        Criterion("inc2", "inclusion", "semantic", "measurable disease per RECIST", "…"),
        Criterion("exc1", "exclusion", "semantic", "active CNS metastasis", "…"),
    ]
    # semantic judge: measurable-disease -> INSUFFICIENT (not stated); CNS -> INSUFFICIENT
    monkeypatch.setattr(tm, "judge_semantic",
        lambda crit, prof: ("INSUFFICIENT", "not stated", "not stated", "low"))
    card = tm.match(p, "NCT1", "A trial", "RECRUITING", crits)
    assert card.verdict == "Needs verification"
    assert card.n_met == 1  # only the age inclusion
    assert any("measurable" in v.lower() or "cns" in v.lower() for v in card.to_verify)
    # each result carries how it was decided, so the UI can label rule vs model judgment
    assert [r.ctype for r in card.criteria] == ["structured", "semantic", "semantic"]
