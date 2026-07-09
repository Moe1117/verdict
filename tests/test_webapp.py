"""The live API: POST /api/resolve returns a web Card for a pasted claim, and GET
/api/resolve/stream streams the pipeline as it runs. run_live + the plain-LLM foil are mocked, so
these tests need no network and no API key — they pin the HTTP contract, error handling, and the
SSE framing the UI depends on."""
import threading

import pytest
from fastapi.testclient import TestClient

from verdict import webapp
from verdict.gates import EvidenceRow
from verdict.verdict import evaluate


@pytest.fixture
def client():
    return TestClient(webapp.app)


def _canned_card():
    rows = [EvidenceRow(citation="c", source_id="PMID:1", design="meta-analysis of rcts",
                        direction=1, population_match=True, n_int=8000, year=2021, finding="benefit")]
    return evaluate("drugX reduces mortality in adults", rows)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_resolve_returns_live_card(client, monkeypatch):
    monkeypatch.setattr(webapp, "run_live", lambda claim, k=8, on_event=None, **kw: _canned_card())
    monkeypatch.setattr(webapp, "plain_llm_baseline",
                        lambda claim: {"answer": "Yes", "confidence": "high", "text": "Yes, obviously."})
    r = client.post("/api/resolve", json={"claim": "drugX reduces mortality in adults"})
    assert r.status_code == 200
    c = r.json()
    assert c["id"] == "LIVE"
    assert c["verdict"] == "Supported"
    assert c["baseline"]["answer"] == "Yes"
    for key in ("gate_trace", "ledger", "certainty", "certainty_domains", "timeline"):
        assert key in c


@pytest.mark.parametrize("bad", ["", "  ", "no"])
def test_resolve_rejects_too_short_claim(client, bad):
    r = client.post("/api/resolve", json={"claim": bad})
    assert r.status_code == 422


def test_resolve_rejects_oversized_claim(client):
    """An unbounded claim would be embedded verbatim into paid Claude prompts — cap it."""
    r = client.post("/api/resolve", json={"claim": "x " * 5000})
    assert r.status_code == 422


def test_stream_rejects_oversized_claim(client):
    r = client.get("/api/resolve/stream", params={"claim": "x " * 5000})
    assert r.status_code == 422


def test_resolve_returns_429_when_saturated(client, monkeypatch):
    """The unauthenticated resolve endpoint is bounded by a concurrency cap: no free slot -> 429,
    never an unbounded fan-out of paid Claude calls."""
    monkeypatch.setattr(webapp, "_slots", threading.Semaphore(0))  # no capacity
    r = client.post("/api/resolve", json={"claim": "drugX reduces mortality in adults"})
    assert r.status_code == 429


def test_stream_returns_429_when_saturated(client, monkeypatch):
    monkeypatch.setattr(webapp, "_slots", threading.Semaphore(0))
    r = client.get("/api/resolve/stream", params={"claim": "drugX reduces mortality in adults"})
    assert r.status_code == 429


def test_cors_is_scoped_to_localhost_not_wildcard(client):
    """CORS must not echo an arbitrary origin — a wildcard would let any page drive paid spend."""
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5175"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5175"
    evil = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert evil.headers.get("access-control-allow-origin") not in ("*", "http://evil.example")


def test_resolve_hides_engine_failure_and_never_leaks_secrets(client, monkeypatch):
    def boom(claim, k=8, on_event=None, **kw):
        raise RuntimeError("ANTHROPIC_API_KEY sk-ant-secret is invalid")
    monkeypatch.setattr(webapp, "run_live", boom)
    r = client.post("/api/resolve", json={"claim": "drugX reduces mortality in adults"})
    assert r.status_code == 502
    assert "sk-ant-secret" not in r.text and "ANTHROPIC_API_KEY" not in r.text


def test_stream_emits_progress_then_final_card(client, monkeypatch):
    def fake(claim, k=8, on_event=None, **kw):
        if on_event:
            on_event({"stage": "parse", "measurable": True, "query": "q"})
            on_event({"stage": "study", "source_id": "PMID:1", "design": "rct",
                      "direction": 1, "integrity_ok": True, "finding": "x"})
        return _canned_card()
    monkeypatch.setattr(webapp, "run_live", fake)
    monkeypatch.setattr(webapp, "plain_llm_baseline", lambda claim: None)
    r = client.get("/api/resolve/stream", params={"claim": "drugX reduces mortality in adults"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    body = r.text
    assert "event: progress" in body
    assert "event: card" in body
    assert '"id": "LIVE"' in body


def test_stream_rejects_too_short_claim(client):
    r = client.get("/api/resolve/stream", params={"claim": "no"})
    assert r.status_code == 422
