from verdict import investigate
from verdict.investigate import Citation, Investigation, verify_citations


# ---- Task 1: citation-verification grounding gate -------------------------------------------------

def test_ungrounded_found_downgrades_to_abstain():
    # a FOUND verdict whose cited IDs were never retrieved must downgrade to abstain
    inv = Investigation(kind="antibody", verdict="FOUND_VALIDATION",
                        cited=[Citation(id="PMID:999", kind="pubmed", title="x", why="y")],
                        reasoning="r", steps=["searched"], grounded=False)
    out = verify_citations(inv, retrieved={"PMID:111"})  # 999 not retrieved
    assert out.verdict == "NO_VALIDATION_FOUND"
    assert out.cited == [] and out.grounded is False


def test_grounded_found_keeps_only_retrieved_citations():
    inv = Investigation(kind="antibody", verdict="FOUND_VALIDATION",
                        cited=[Citation(id="PMID:111", kind="pubmed", title="real", why="KO"),
                               Citation(id="PMID:999", kind="pubmed", title="hallucinated", why="z")],
                        reasoning="r", steps=[], grounded=False)
    out = verify_citations(inv, retrieved={"PMID:111"})
    assert out.verdict == "FOUND_VALIDATION"
    assert [c.id for c in out.cited] == ["PMID:111"]  # 999 stripped
    assert out.grounded is True


def test_provenance_downgrades_to_partial_without_grounded_reference():
    inv = Investigation(kind="cell_line", verdict="PROVENANCE_CHAIN",
                        cited=[Citation(id="CVCL_2451", kind="cellosaurus", title="", why="")],
                        reasoning="r", steps=[], grounded=False)
    # CVCL grounded but no PubMed primary reference retrieved -> PARTIAL (still grounded on the CVCL)
    out = verify_citations(inv, retrieved={"CVCL_2451"})
    assert out.verdict == "PARTIAL"
    assert out.grounded is True


# ---- Task 2: Retriever (real HTTP tools + retrieval log) ------------------------------------------

def test_retriever_pubmed_search_logs_pmids(monkeypatch):
    calls = {}
    def fake_get(url, timeout=12):
        calls["url"] = url
        return '{"esearchresult": {"idlist": ["111", "222"]}}'
    monkeypatch.setattr(investigate, "_http_get", fake_get)
    r = investigate.Retriever(email="x@y.z")
    ids = r.pubmed_search("GABARAP knockout antibody", retmax=5)
    assert ids == ["111", "222"]
    assert "PMID:111" in r.retrieved and "PMID:222" in r.retrieved
    assert "esearch.fcgi" in calls["url"] and "GABARAP" in calls["url"]


def test_retriever_pubmed_fetch_returns_text_and_logs(monkeypatch):
    monkeypatch.setattr(investigate, "_http_get", lambda url, timeout=12: "1. Title.\n\nAbstract: signal lost in KO.")
    r = investigate.Retriever(email="x@y.z")
    out = r.pubmed_fetch(["111"])
    assert "signal lost" in out["111"]
    assert "PMID:111" in r.retrieved


def test_retriever_cellosaurus_logs_cvcl_and_pmids(monkeypatch):
    body = ('{"Cellosaurus":{"cell-line-list":[{"accession-list":[{"type":"primary","value":"CVCL_2451"}],'
            '"comment-list":[{"category":"Problematic cell line","value":"Contaminated. Is PSN1."}],'
            '"reference-list":[{"internal-resources":[{"accession":"PubMed=1234567"}]}]}]}}')
    monkeypatch.setattr(investigate, "_http_get", lambda url, timeout=12: body)
    r = investigate.Retriever(email="x@y.z")
    rec = r.cellosaurus_lookup("CVCL_2451")
    assert rec["cvcl"] == "CVCL_2451" and "PSN1" in rec["problem"]
    assert "CVCL_2451" in r.retrieved and "PMID:1234567" in r.retrieved


def test_retriever_http_error_degrades(monkeypatch):
    def boom(url, timeout=12): raise OSError("network")
    monkeypatch.setattr(investigate, "_http_get", boom)
    r = investigate.Retriever(email="x@y.z")
    assert r.pubmed_search("x") == []            # never raises
    assert r.cellosaurus_lookup("CVCL_x") == {}  # never raises
