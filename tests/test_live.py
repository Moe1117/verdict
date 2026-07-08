"""The live pipeline (parse -> retrieve -> extract -> gates) is wired and orchestrates
correctly — proven with the two Claude calls mocked, so no API key is needed to test it."""
from verdict import extract, parse, retrieve
from verdict import verdict as vmod
from verdict.gates import EvidenceRow, Verdict
from verdict.parse import ClaimTuple
from verdict.retrieve import Source


def _src(pid):
    return Source(kind="pubmed", id=pid, title=f"Study {pid}", authors="A", journal="J", year="2020", url="u")


def test_run_live_orchestrates_to_a_verdict(monkeypatch):
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "drugX mortality"))
    monkeypatch.setattr(retrieve, "search_pubmed", lambda q, retmax=8: [_src("PMID:1"), _src("PMID:2")])
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: "transient abstract text")
    rows = {
        "PMID:1": EvidenceRow(citation="c", design="meta-analysis of rcts", direction=1, population_match=True),
        "PMID:2": EvidenceRow(citation="c", design="rct", direction=1, population_match=True, n_int=5000),
    }
    monkeypatch.setattr(extract, "extract_row", lambda s, a, c: rows[s.id])
    card = vmod.run_live("drugX improves survival in adults")
    assert card.verdict is Verdict.SUPPORTED
    assert len(card.ledger) == 2


def test_input_guard_returns_undecidable(monkeypatch):
    ct = ClaimTuple(raw="x", agent="?", outcome="vibes", population="?", direction=1, measurable=False)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, ""))
    card = vmod.run_live("does this vibe well")
    assert card.verdict is Verdict.UNDECIDABLE
    assert card.gate_trace[0].gate == "input-guard"


def test_extract_row_maps_structured_output(monkeypatch):
    payload = {"design": "rct", "direction": 1, "population_match": True, "outcome_match": False,
               "dramatic_effect": False, "integrity_ok": True, "n_int": 1200, "year": 2019,
               "sig": "significant", "finding": "reduced the surrogate endpoint",
               "effect_point": 0.75, "ci_low": 0.6, "ci_high": 0.9}
    monkeypatch.setattr(extract, "call_tool", lambda system, user, tool, max_tokens=1200: payload)
    ct = ClaimTuple(raw="x", agent="drugX", outcome="CV events", population="adults", direction=-1)
    r = extract.extract_row(_src("PMID:9"), "abstract", ct)
    assert isinstance(r, EvidenceRow)
    assert r.design == "rct" and r.n_int == 1200 and r.outcome_match is False
    assert r.effect_point == 0.75 and r.sig == "significant"
