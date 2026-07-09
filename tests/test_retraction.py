"""Live retraction immunity.

A study that PubMed has marked "Retracted Publication" (or "Expression of Concern") is
flagged inert DETERMINISTICALLY at retrieval — read from the database's own publication
type, NOT from the LLM's reading of the abstract. The deterministic database fact overrides
whatever the extractor said, so a retracted study can never re-enter the verdict path even if
the model failed to notice the retraction. This closes fraud-immunity for the LIVE lane
(the frozen demo already excludes known-bad studies via the curated integrity records).
"""
from verdict import extract, parse, retrieve
from verdict import verdict as vmod
from verdict.gates import EvidenceRow, Verdict
from verdict.parse import ClaimTuple
from verdict.retrieve import Source, retraction_severity, search_pubmed


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def test_retraction_severity_reads_pubmed_pubtypes():
    assert retraction_severity(["Journal Article", "Retracted Publication"]) == "retracted"
    assert retraction_severity(["Journal Article", "Expression of Concern"]) == "expression_of_concern"
    assert retraction_severity(["Journal Article", "Randomized Controlled Trial"]) == ""
    assert retraction_severity([]) == ""
    assert retraction_severity(None) == ""


def test_retraction_severity_tolerates_string_input():
    """Defensive: if the source ever yields a bare string instead of a list, we must NOT
    iterate it character-by-character and silently miss the retraction."""
    assert retraction_severity("Retracted Publication") == "retracted"
    assert retraction_severity("Expression of Concern") == "expression_of_concern"
    assert retraction_severity("Journal Article") == ""


def test_search_pubmed_flags_retracted_source(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        if "esearch" in url:
            return _Resp({"esearchresult": {"idlist": ["111", "222"]}})
        return _Resp({"result": {
            "uids": ["111", "222"],
            "111": {"title": "Clean study", "pubtype": ["Journal Article", "Randomized Controlled Trial"],
                    "fulljournalname": "J", "pubdate": "2020", "authors": []},
            "222": {"title": "Retracted study", "pubtype": ["Journal Article", "Retracted Publication"],
                    "fulljournalname": "J", "pubdate": "2021", "authors": []},
        }})
    monkeypatch.setattr(retrieve.httpx, "get", fake_get)
    monkeypatch.setattr(retrieve, "_pause", lambda: None)
    srcs = {s.id: s for s in search_pubmed("q")}
    assert srcs["PMID:111"].integrity_severity == ""
    assert srcs["PMID:222"].integrity_severity == "retracted"


def test_live_path_marks_retracted_row_inert_over_the_llm(monkeypatch):
    ct = ClaimTuple(raw="x", agent="ivm", outcome="mortality", population="covid", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "ivm covid"))
    good = Source(kind="pubmed", id="PMID:1", title="t", authors="", journal="J", year="2022", url="u1")
    fraud = Source(kind="pubmed", id="PMID:2", title="t", authors="", journal="J", year="2021", url="u2",
                   integrity_severity="retracted")
    monkeypatch.setattr(retrieve, "search_pubmed", lambda q, retmax=8: [good, fraud])
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: "abstract")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [])

    # The LLM (mocked) NAIVELY reports BOTH studies as sound and supporting the claim.
    def fake_extract(s, a, c):
        return EvidenceRow(citation="c", source_id=s.id, design="rct", direction=1,
                           population_match=True, n_int=2000, integrity_ok=True)
    monkeypatch.setattr(extract, "extract_row", fake_extract)

    card = vmod.run_live("ivermectin reduces mortality in covid")
    byid = {r.source_id: r for r in card.ledger}
    # deterministic override: the retracted study is inert even though the LLM said integrity_ok=True
    assert byid["PMID:2"].integrity_ok is False
    assert "RETRACT" in byid["PMID:2"].integrity_note.upper()
    assert "u2" in byid["PMID:2"].integrity_note  # cites the source record
    # the clean study is untouched
    assert byid["PMID:1"].integrity_ok is True
    # and the verdict path actually screened the retracted study out
    assert any(g.gate == "integrity-screen" for g in card.gate_trace)
