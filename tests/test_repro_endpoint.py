from fastapi.testclient import TestClient

from verdict import repro, webapp

BODY = {"methods": "Cells were the GR-M line, cultured in DMEM with 10% FBS at 37C."}


def _reset_cap(monkeypatch, cap):
    monkeypatch.setattr(webapp, "_DAILY_CAP", cap)
    webapp._day_state["day"] = None
    webapp._day_state["count"] = 0


def test_repro_endpoint_degrades_no_502(monkeypatch):
    # extraction failure (call_tool RAISES) must yield a 200 valid report, never a 502.
    def boom(*a, **k):
        raise RuntimeError("model returned no structured tool call")
    monkeypatch.setattr(repro, "call_tool", boom)
    _reset_cap(monkeypatch, 0)  # cap off for this test
    r = TestClient(webapp.app).post("/api/repro", json=BODY)
    assert r.status_code == 200, r.text
    assert r.json()["report"]["n_fail"] == 0


def test_repro_daily_cap_returns_429_over_limit(monkeypatch):
    # a public, unauthenticated, paid endpoint must cap total daily spend.
    monkeypatch.setattr(webapp, "repro_review", lambda m: repro.ReproReport(
        findings=[], verdict="Needs verification", n_fail=0, n_pass=0, n_insufficient=0))
    _reset_cap(monkeypatch, 2)
    c = TestClient(webapp.app)
    assert c.post("/api/repro", json=BODY).status_code == 200
    assert c.post("/api/repro", json=BODY).status_code == 200
    assert c.post("/api/repro", json=BODY).status_code == 429  # over the daily cap


def test_repro_daily_cap_zero_means_unlimited(monkeypatch):
    monkeypatch.setattr(webapp, "repro_review", lambda m: repro.ReproReport(
        findings=[], verdict="Submission-ready", n_fail=0, n_pass=0, n_insufficient=0))
    _reset_cap(monkeypatch, 0)
    c = TestClient(webapp.app)
    for _ in range(5):
        assert c.post("/api/repro", json=BODY).status_code == 200
