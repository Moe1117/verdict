from fastapi.testclient import TestClient

from verdict import investigate, webapp


def _reset(monkeypatch):
    monkeypatch.setattr(webapp, "_DAILY_CAP", 0)
    webapp._day_state["day"] = None
    webapp._day_state["count"] = 0


def test_investigate_endpoint_returns_report(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(webapp, "investigate_antibody",
        lambda **kw: investigate.Investigation(
            kind="antibody", verdict="FOUND_VALIDATION",
            cited=[investigate.Citation(id="PMID:111", kind="pubmed", title="t", why="KO")],
            reasoning="r", steps=["searched", "read PMID:111"], grounded=True))
    r = TestClient(webapp.app).post("/api/investigate",
                                    json={"kind": "antibody", "name": "8H5", "target": "GABARAP"})
    assert r.status_code == 200
    body = r.json()["investigation"]
    assert body["verdict"] == "FOUND_VALIDATION" and body["cited"][0]["id"] == "PMID:111"
    assert body["steps"]  # the agentic trail is returned for the UI


def test_investigate_endpoint_degrades(monkeypatch):
    _reset(monkeypatch)
    def boom(**kw):
        raise RuntimeError("api down")
    monkeypatch.setattr(webapp, "investigate_antibody", boom)
    r = TestClient(webapp.app).post("/api/investigate", json={"kind": "antibody", "name": "x"})
    assert r.status_code == 200  # graceful, never 502
    assert r.json()["investigation"]["verdict"] == "INCONCLUSIVE"
