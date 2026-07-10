import glob
import json


def test_deck_cards_have_required_shape():
    files = glob.glob("benchmark/trialdeck/case*.json")
    assert files, "no frozen deck built yet"
    for f in files:
        d = json.load(open(f))
        assert d["cards"], f"{f} has no trials"
        for c in d["cards"]:
            assert c["verdict"] in ("Likely eligible", "Ineligible", "Needs verification")
            assert isinstance(c["criteria"], list)
            assert set(("nct_id", "url", "to_verify", "n_to_verify")) <= set(c)
