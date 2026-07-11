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


# ---- Task 3: the bounded agentic loop ------------------------------------------------------------

class _FakeBlock:
    def __init__(self, **kw): self.__dict__.update(kw)

class _FakeMsg:
    def __init__(self, blocks): self.content = blocks

class _ScriptedClient:
    """Returns a fixed sequence of assistant turns (one per create call)."""
    def __init__(self, turns):
        self._turns = turns
        self.messages = self
    def create(self, **kw):
        return self._turns.pop(0)

class _AlwaysSearchClient:
    """Never emits — always asks for another search (exercises the cap/degrade path)."""
    def __init__(self):
        self.messages = self
    def create(self, **kw):
        return _FakeMsg([_FakeBlock(type="tool_use", id="t", name="pubmed_search", input={"query": "x"})])


def test_run_investigation_executes_tools_then_emits_grounded(monkeypatch):
    monkeypatch.setattr(investigate, "_http_get",
                        lambda url, timeout=12: '{"esearchresult":{"idlist":["111"]}}' if "esearch" in url else "KO abstract")
    turns = [
        _FakeMsg([_FakeBlock(type="tool_use", id="t1", name="pubmed_search", input={"query": "GABARAP 8H5 knockout"})]),
        _FakeMsg([_FakeBlock(type="tool_use", id="t2", name="emit_investigation",
                             input={"verdict": "FOUND_VALIDATION", "reasoning": "KO abolished signal",
                                    "cited": [{"id": "PMID:111", "kind": "pubmed", "title": "t", "why": "KO"}],
                                    "steps": ["searched GABARAP 8H5", "read PMID:111"]})]),
    ]
    r = investigate.Retriever(email="x@y.z")
    inv = investigate.run_investigation("Investigate antibody 8H5 (GABARAP).", r,
                                        client=_ScriptedClient(turns), kind="antibody")
    assert inv.verdict == "FOUND_VALIDATION" and inv.grounded is True
    assert [c.id for c in inv.cited] == ["PMID:111"]
    assert "read PMID:111" in inv.steps


def test_run_investigation_strips_ungrounded_citation(monkeypatch):
    # the model emits without ever retrieving PMID:999 -> stripped -> downgraded to abstain
    monkeypatch.setattr(investigate, "_http_get", lambda url, timeout=12: '{"esearchresult":{"idlist":[]}}')
    turns = [_FakeMsg([_FakeBlock(type="tool_use", id="t", name="emit_investigation",
                                  input={"verdict": "FOUND_VALIDATION", "reasoning": "made up",
                                         "cited": [{"id": "PMID:999", "kind": "pubmed"}], "steps": []})])]
    inv = investigate.run_investigation("t", investigate.Retriever(), client=_ScriptedClient(turns), kind="antibody")
    assert inv.verdict == "NO_VALIDATION_FOUND" and inv.cited == []


def test_run_investigation_caps_and_degrades(monkeypatch):
    monkeypatch.setattr(investigate, "_http_get", lambda url, timeout=12: '{"esearchresult":{"idlist":[]}}')
    inv = investigate.run_investigation("t", investigate.Retriever(), client=_AlwaysSearchClient(),
                                        kind="antibody", max_steps=3)
    assert inv.verdict == "INCONCLUSIVE"


# ---- Task 4: antibody / cell-line entrypoints ----------------------------------------------------

def test_investigate_antibody_builds_task_and_runs(monkeypatch):
    seen = {}
    def fake_run(task, retriever, client=None, kind="antibody", **kw):
        seen["task"], seen["kind"] = task, kind
        return investigate.Investigation(kind=kind, verdict="NO_VALIDATION_FOUND")
    monkeypatch.setattr(investigate, "run_investigation", fake_run)
    inv = investigate.investigate_antibody("anti-GABARAP 8H5", target="GABARAP")
    assert seen["kind"] == "antibody" and "GABARAP" in seen["task"] and "8H5" in seen["task"]
    assert inv.verdict == "NO_VALIDATION_FOUND"


def test_investigate_cell_line_builds_task(monkeypatch):
    seen = {}
    def fake_run(task, retriever, client=None, kind="antibody", **kw):
        seen["task"], seen["kind"] = task, kind
        return investigate.Investigation(kind="cell_line", verdict="PARTIAL")
    monkeypatch.setattr(investigate, "run_investigation", fake_run)
    investigate.investigate_cell_line("GR-M", iclac_id="ICLAC-00538", cvcl="CVCL_2451")
    assert seen["kind"] == "cell_line" and "GR-M" in seen["task"] and "CVCL_2451" in seen["task"]
