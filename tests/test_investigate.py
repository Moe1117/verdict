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


def test_verify_normalizes_id_forms_before_matching():
    # Claude emits ids in many forms (bare number, 'PMID: 30..', a cvcl in lowercase); each must be
    # canonicalized so it matches the retrieval log — otherwise a real, retrieved citation is wrongly stripped.
    inv = Investigation(kind="antibody", verdict="FOUND_VALIDATION",
                        cited=[Citation(id="30679523", kind="pubmed", title="t", why="KO"),      # bare number
                               Citation(id="PMID: 111", kind="pubmed", title="t", why="x"),      # spaced
                               Citation(id="cvcl_2451", kind="misc", title="", why="")])          # lc cvcl
    out = verify_citations(inv, retrieved={"PMID:30679523", "PMID:111", "CVCL_2451"})
    assert out.verdict == "FOUND_VALIDATION" and out.grounded is True
    assert {c.id for c in out.cited} == {"PMID:30679523", "PMID:111", "CVCL_2451"}
    # kind is re-derived from the canonical id (not trusted from the model)
    assert {c.kind for c in out.cited if c.id.startswith("PMID")} == {"pubmed"}


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


# ---- Task 5: PMC open-access FULL-TEXT escalation --------------------------------------------------
# Antibody genetic-validation usually lives in the Methods full text, not the abstract. pmc_fetch maps
# a PMID -> its PMC open-access record and returns full text, so the agent stops abstaining when the
# evidence is real but buried. Citations stay keyed to the PMID (grounding gate is unchanged).

def test_retriever_pmc_fetch_returns_fulltext_and_logs(monkeypatch):
    def fake_get(url, timeout=12):
        if "elink" in url:
            return '{"linksets":[{"linksetdbs":[{"dbto":"pmc","links":["6349789"]}]}]}'
        return "<article><body><p>anti-GABARAP 8H5 signal was abolished in GABARAP-knockout cells.</p></body></article>"
    monkeypatch.setattr(investigate, "_http_get", fake_get)
    r = investigate.Retriever(email="x@y.z")
    out = r.pmc_fetch(["30679523"])
    assert "abolished" in out["30679523"]        # full-text body, tags stripped
    assert "<p>" not in out["30679523"]           # XML tags removed
    assert "PMID:30679523" in r.retrieved         # logged only because full text was retrieved
    assert r.n_pmc == 1


def test_retriever_pmc_fetch_no_oa_record_degrades(monkeypatch):
    # A PMID with no PMC open-access link yields nothing — and is NOT logged as retrieved (so it can't
    # be cited off the back of a full-text read that never happened).
    monkeypatch.setattr(investigate, "_http_get",
                        lambda url, timeout=12: '{"linksets":[{"linksetdbs":[]}]}' if "elink" in url else "<article/>")
    r = investigate.Retriever(email="x@y.z")
    assert r.pmc_fetch(["999"]) == {}
    assert "PMID:999" not in r.retrieved


def test_retriever_pmc_fetch_http_error_degrades(monkeypatch):
    def boom(url, timeout=12): raise OSError("network")
    monkeypatch.setattr(investigate, "_http_get", boom)
    r = investigate.Retriever(email="x@y.z")
    assert r.pmc_fetch(["111"]) == {}            # never raises


def test_pmc_fetch_cap_enforced_in_dispatch(monkeypatch):
    monkeypatch.setattr(investigate, "_http_get", lambda url, timeout=12: '{"linksets":[]}')
    r = investigate.Retriever(email="x@y.z")
    caps = {"search": 3, "fetch": 6, "pmc": 1}
    investigate._dispatch(r, "pmc_fetch", {"pmids": ["1"]}, caps)          # n_pmc 0 -> 1
    out = investigate._dispatch(r, "pmc_fetch", {"pmids": ["2"]}, caps)    # 1 == cap -> exhausted
    assert "budget" in out


def test_run_investigation_uses_pmc_fulltext_then_grounds(monkeypatch):
    def fake_get(url, timeout=12):
        if "esearch" in url:
            return '{"esearchresult":{"idlist":["30679523"]}}'
        if "elink" in url:
            return '{"linksets":[{"linksetdbs":[{"dbto":"pmc","links":["6349789"]}]}]}'
        return "<article><body><p>GABARAP-knockout abolished the 8H5 signal.</p></body></article>"
    monkeypatch.setattr(investigate, "_http_get", fake_get)
    turns = [
        _FakeMsg([_FakeBlock(type="tool_use", id="t1", name="pubmed_search", input={"query": "GABARAP 8H5 knockout"})]),
        _FakeMsg([_FakeBlock(type="tool_use", id="t2", name="pmc_fetch", input={"pmids": ["30679523"]})]),
        _FakeMsg([_FakeBlock(type="tool_use", id="t3", name="emit_investigation",
                             input={"verdict": "FOUND_VALIDATION", "reasoning": "KO abolished signal (full text)",
                                    "cited": [{"id": "PMID:30679523", "kind": "pubmed", "title": "t", "why": "KO"}],
                                    "steps": ["searched", "read PMC full text PMID:30679523"]})]),
    ]
    r = investigate.Retriever(email="x@y.z")
    inv = investigate.run_investigation("Investigate 8H5 (GABARAP).", r,
                                        client=_ScriptedClient(turns), kind="antibody")
    assert inv.verdict == "FOUND_VALIDATION" and inv.grounded is True
    assert [c.id for c in inv.cited] == ["PMID:30679523"]
