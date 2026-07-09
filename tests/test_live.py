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
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [])
    rows = {
        "PMID:1": EvidenceRow(citation="c", design="meta-analysis of rcts", direction=1, population_match=True),
        "PMID:2": EvidenceRow(citation="c", design="rct", direction=1, population_match=True, n_int=5000),
    }
    monkeypatch.setattr(extract, "extract_row", lambda s, a, c: rows[s.id])
    card = vmod.run_live("drugX improves survival in adults")
    assert card.verdict is Verdict.SUPPORTED
    assert len(card.ledger) == 2


def test_run_live_adds_clinicaltrials_results(monkeypatch):
    """A ClinicalTrials.gov trial WITH posted results is retrieved + extracted alongside PubMed."""
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "q"))
    monkeypatch.setattr(retrieve, "search_pubmed", lambda q, retmax=8: [])
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: "")
    trial = Source(kind="clinicaltrials", id="NCT:1", title="t", authors="", journal="ClinicalTrials.gov", year="", url="u")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [trial])
    monkeypatch.setattr(retrieve, "fetch_trial", lambda nct: "TRIAL: posted results, negative primary endpoint")
    monkeypatch.setattr(extract, "extract_row", lambda s, text, c:
                        EvidenceRow(citation="c", source_id=s.id, design="rct", direction=-1,
                                    population_match=True, n_int=2000))
    card = vmod.run_live("drugX improves survival")
    assert any(r.source_id == "NCT:1" for r in card.ledger)


def test_run_live_skips_clinicaltrials_without_results(monkeypatch):
    """A registered trial with NO posted results is not evidence — it is never extracted."""
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "q"))
    monkeypatch.setattr(retrieve, "search_pubmed", lambda q, retmax=8: [])
    trial = Source(kind="clinicaltrials", id="NCT:9", title="t", authors="", journal="ClinicalTrials.gov", year="", url="u")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [trial])
    monkeypatch.setattr(retrieve, "fetch_trial", lambda nct: None)   # no posted results
    called: list = []
    monkeypatch.setattr(extract, "extract_row",
                        lambda s, text, c: called.append(s) or EvidenceRow(citation="c", design="rct", direction=1, population_match=True))
    card = vmod.run_live("drugX improves survival")
    assert card.ledger == [] and called == []


def test_input_guard_returns_undecidable(monkeypatch):
    ct = ClaimTuple(raw="x", agent="?", outcome="vibes", population="?", direction=1, measurable=False)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, ""))
    card = vmod.run_live("does this vibe well")
    assert card.verdict is Verdict.UNDECIDABLE
    assert card.gate_trace[0].gate == "input-guard"


def test_model_falls_back_on_empty_or_unset(monkeypatch):
    """VERDICT_MODEL='' (as in a freshly-copied .env) must NOT blank the model — a real
    400 on the live path. Empty is treated as unset; read at call time, not import time."""
    monkeypatch.delenv("VERDICT_MODEL", raising=False)
    assert parse.model() == "claude-sonnet-5"
    monkeypatch.setenv("VERDICT_MODEL", "")
    assert parse.model() == "claude-sonnet-5"
    monkeypatch.setenv("VERDICT_MODEL", "claude-opus-4-8")
    assert parse.model() == "claude-opus-4-8"


def test_extract_row_cleans_nct_source_id(monkeypatch):
    """A ClinicalTrials.gov source id is 'NCT:NCT0123...' — the display id must not double the
    registry prefix ('NCTNCT0123'); PMIDs keep their prefix."""
    payload = {"design": "rct", "direction": 1, "population_match": True, "outcome_match": True,
               "dramatic_effect": False, "integrity_ok": True, "n_int": 100, "year": 2020,
               "sig": "significant", "finding": "x"}
    monkeypatch.setattr(extract, "call_tool", lambda system, user, tool, max_tokens=1200: payload)
    ct = ClaimTuple(raw="x", agent="d", outcome="o", population="p", direction=1)
    nct = Source(kind="clinicaltrials", id="NCT:NCT05579977", title="t", authors="", journal="CT.gov", year="", url="u")
    assert extract.extract_row(nct, "abstract", ct).source_id == "NCT05579977"
    assert extract.extract_row(_src("PMID:12345"), "abstract", ct).source_id == "PMID:12345"


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
