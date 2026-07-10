import json
from verdict import trials

def test_parse_search(monkeypatch):
    raw = json.load(open("tests/fixtures/ctgov_search.json"))
    monkeypatch.setattr(trials, "_get_json", lambda url: raw)
    got = trials.search_candidates_by_condition("non-small cell lung cancer", page_size=3)
    assert len(got) >= 1
    assert got[0].nct_id.startswith("NCT") and got[0].title

def test_parse_eligibility(monkeypatch):
    raw = json.load(open("tests/fixtures/ctgov_study.json"))
    monkeypatch.setattr(trials, "_get_json", lambda url: raw)
    elig = trials.get_eligibility("NCT06927986")
    assert "Inclusion" in elig.text or "inclusion" in elig.text.lower()
    assert elig.nct_id == "NCT06927986"
