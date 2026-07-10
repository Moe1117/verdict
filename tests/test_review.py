from verdict import trialmatch as tm, trials
from verdict.trialmatch import PatientProfile, TrialCard, card_to_dict, rank_cards


def _card(nct, verdict, nverify):
    return TrialCard(nct, "t", "RECRUITING", "u", verdict, [], ["x"] * nverify, 1, 0, nverify)


def test_rank_orders_eligible_first_then_fewest_open():
    cards = [_card("A", "Ineligible", 0), _card("B", "Needs verification", 3),
             _card("C", "Likely eligible", 0), _card("D", "Needs verification", 1)]
    order = [c.nct_id for c in rank_cards(cards)]
    assert order == ["C", "D", "B", "A"]


def test_card_to_dict_is_json_safe():
    c = _card("NCT1", "Needs verification", 2)
    d = card_to_dict(c)
    import json
    json.dumps(d)  # must not raise
    assert d["nct_id"] == "NCT1" and d["n_to_verify"] == 2


def test_review_orchestrates(monkeypatch):
    monkeypatch.setattr(tm, "extract_profile", lambda note: PatientProfile(age=62, raw_note=note))
    monkeypatch.setattr(trials, "search_candidates_by_condition",
        lambda cond, page_size=5, status="RECRUITING": [trials.Candidate("NCT1", "t", "RECRUITING")])
    monkeypatch.setattr(trials, "get_eligibility",
        lambda nct: trials.Eligibility(nct, "Inclusion: Aged 18-75", "18 Years", "75 Years", "ALL"))
    monkeypatch.setattr(tm, "extract_criteria", lambda text: [])
    cards = tm.review("62F metastatic NSCLC ...", condition="non-small cell lung cancer")
    assert isinstance(cards, list) and cards and isinstance(cards[0], TrialCard)
