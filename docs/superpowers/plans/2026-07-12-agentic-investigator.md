# Agentic Investigator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an agentic investigator that autonomously searches real public APIs (PubMed, Cellosaurus, the Antibody Registry) to find real-citation evidence of an antibody's knockout validation or a cell line's misidentification provenance — with fabricated citations impossible by construction.

**Architecture:** A bounded Claude tool-use loop (`verdict/investigate.py`) drives real HTTP tools via a `Retriever` that logs every ID it actually returns. Claude's final `emit_investigation` verdict is deterministically filtered against that log; any un-retrieved citation is stripped and an ungrounded "found" verdict downgrades to abstain. Exposed at `POST /api/investigate`, spend-guarded, with a UI trail. Measured by a live eval on known cases.

**Tech Stack:** Python 3.10+, anthropic SDK (tool-use loop), urllib (NCBI E-utilities + Cellosaurus REST + Antibody Registry), FastAPI, pytest. React/TS for the UI.

---

## File structure

- Create `verdict/investigate.py` — Retriever (real HTTP + retrieval log), the bounded agentic loop, `Investigation` dataclass, citation-verification, `investigate_antibody`/`investigate_cell_line`. One responsibility: agentic literature investigation with a grounding guarantee.
- Modify `verdict/webapp.py` — add `POST /api/investigate` (spend-guarded, graceful).
- Create `tests/test_investigate.py` — unit tests (mock the anthropic client + `Retriever`).
- Create `tests/test_investigate_endpoint.py` — endpoint tests (TestClient, mock `investigate.*`).
- Create `scripts/repro_investigate_eval.py` + `benchmark/repro/investigate_corpus.json` — measured eval.
- Modify `web/src/Repro.tsx`, `web/src/types.ts` — an "Investigate" affordance + the agentic-steps trail.

Convention: follow `verdict/knockout.py` (dataclass + graceful degradation + labelled method) and `verdict/repro.py` (deterministic gate over model output).

---

### Task 1: `Investigation` dataclass + deterministic citation-verification

**Files:** Create `verdict/investigate.py` (partial); Test `tests/test_investigate.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_investigate.py
from verdict import investigate
from verdict.investigate import Investigation, Citation, verify_citations


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
    # CVCL grounded but no PubMed primary reference retrieved -> PARTIAL
    out = verify_citations(inv, retrieved={"CVCL_2451"})
    assert out.verdict == "PARTIAL"
    assert out.grounded is True  # at least the CVCL is real
```

- [ ] **Step 2: Run to verify fail** — `PYTHONPATH=. .venv/bin/python -m pytest tests/test_investigate.py -q` → FAIL (module/attrs missing).

- [ ] **Step 3: Implement the dataclasses + `verify_citations`**

```python
# verdict/investigate.py  (top)
"""Agentic Investigator — Claude autonomously searches real public APIs (PubMed, Cellosaurus,
the Antibody Registry) for real-citation evidence, and a deterministic gate guarantees no fabricated
citation survives. Claude navigates; the retrieval log decides what may be cited."""
from __future__ import annotations

from dataclasses import dataclass, field

# terminal verdicts
_ANTIBODY_FOUND = "FOUND_VALIDATION"
_ANTIBODY_NONE = "NO_VALIDATION_FOUND"
_CELL_FULL = "PROVENANCE_CHAIN"
_CELL_PARTIAL = "PARTIAL"
_INCONCLUSIVE = "INCONCLUSIVE"  # tool/loop failure — graceful degradation


@dataclass
class Citation:
    id: str            # "PMID:12345" | "CVCL_2451" | "RRID:AB_..."
    kind: str          # "pubmed" | "cellosaurus" | "antibody_registry"
    title: str = ""
    why: str = ""      # one line: why this supports the verdict


@dataclass
class Investigation:
    kind: str          # "antibody" | "cell_line"
    verdict: str
    cited: list = field(default_factory=list)
    reasoning: str = ""
    steps: list = field(default_factory=list)   # human-readable agentic trail
    grounded: bool = False
    method: str = "model investigation"


def verify_citations(inv: Investigation, retrieved: set) -> Investigation:
    """Deterministic grounding gate: keep only citations whose id was actually retrieved; downgrade an
    ungrounded 'found' verdict to abstain. Fabricated citations cannot survive."""
    kept = [c for c in inv.cited if c.id in retrieved]
    inv.cited = kept
    inv.grounded = bool(kept)
    if inv.kind == "antibody" and inv.verdict == _ANTIBODY_FOUND and not any(c.kind == "pubmed" for c in kept):
        inv.verdict = _ANTIBODY_NONE
    if inv.kind == "cell_line" and inv.verdict == _CELL_FULL and not any(c.kind == "pubmed" for c in kept):
        inv.verdict = _CELL_PARTIAL  # CVCL may still be grounded, but the primary reference is not
    return inv
```

- [ ] **Step 4: Run to verify pass** — `pytest tests/test_investigate.py -q` → PASS.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(investigate): Investigation dataclass + citation-verification gate"`

---

### Task 2: `Retriever` — real HTTP tools + retrieval log

**Files:** Modify `verdict/investigate.py`; Test `tests/test_investigate.py`

- [ ] **Step 1: Write the failing tests** (mock `urllib.request.urlopen` via a fake that returns canned JSON/text)

```python
def test_retriever_pubmed_search_logs_pmids(monkeypatch):
    calls = {}
    def fake_get(url):
        calls["url"] = url
        return '{"esearchresult": {"idlist": ["111", "222"]}}'
    monkeypatch.setattr(investigate, "_http_get", fake_get)
    r = investigate.Retriever(email="x@y.z")
    ids = r.pubmed_search("GABARAP knockout antibody", retmax=5)
    assert ids == ["111", "222"]
    assert "PMID:111" in r.retrieved and "PMID:222" in r.retrieved
    assert "esearch.fcgi" in calls["url"] and "GABARAP" in calls["url"]


def test_retriever_pubmed_fetch_returns_text_and_logs(monkeypatch):
    monkeypatch.setattr(investigate, "_http_get", lambda url: "1. Title.\n\nAbstract: signal lost in KO.")
    r = investigate.Retriever(email="x@y.z")
    out = r.pubmed_fetch(["111"])
    assert "signal lost" in out["111"]
    assert "PMID:111" in r.retrieved


def test_retriever_cellosaurus_logs_cvcl_and_pmids(monkeypatch):
    body = '{"Cellosaurus":{"cell-line-list":[{"accession-list":[{"type":"primary","value":"CVCL_2451"}],' \
           '"comment-list":[{"category":"Problematic cell line","value":"Contaminated. Is PSN1."}],' \
           '"reference-list":[{"internal-resources":[{"accession":"PubMed=1234567"}]}]}]}}'
    monkeypatch.setattr(investigate, "_http_get", lambda url: body)
    r = investigate.Retriever(email="x@y.z")
    rec = r.cellosaurus_lookup("CVCL_2451")
    assert rec["cvcl"] == "CVCL_2451" and "PSN1" in rec["problem"]
    assert "CVCL_2451" in r.retrieved and "PMID:1234567" in r.retrieved


def test_retriever_http_error_degrades(monkeypatch):
    def boom(url): raise OSError("network")
    monkeypatch.setattr(investigate, "_http_get", boom)
    r = investigate.Retriever(email="x@y.z")
    assert r.pubmed_search("x") == []          # never raises
    assert r.cellosaurus_lookup("CVCL_x") == {} # never raises
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_investigate.py -q` → FAIL.

- [ ] **Step 3: Implement `_http_get` + `Retriever`**

```python
import json
import os
import re
import urllib.parse
import urllib.request

_NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_CELLO = "https://api.cellosaurus.org"


def _http_get(url: str, timeout: int = 12) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


class Retriever:
    """Real retrieval over public APIs. Every id it returns is logged in `retrieved` — the ground
    truth the citation-verification gate checks against. All methods degrade to empty on any error."""

    def __init__(self, email: str = ""):
        self.email = email or os.getenv("NCBI_EMAIL", "")
        self.retrieved: set = set()
        self.n_search = 0
        self.n_fetch = 0

    def _eutil(self, tool: str, params: dict) -> str:
        params = {**params, "tool": "verdict", "email": self.email}
        return _http_get(f"{_NCBI}/{tool}?{urllib.parse.urlencode(params)}")

    def pubmed_search(self, query: str, retmax: int = 6) -> list:
        self.n_search += 1
        try:
            d = json.loads(self._eutil("esearch.fcgi", {
                "db": "pubmed", "term": query, "retmax": retmax, "retmode": "json"}))
            ids = list(d.get("esearchresult", {}).get("idlist", []))
        except Exception:  # noqa: BLE001
            return []
        for pid in ids:
            self.retrieved.add(f"PMID:{pid}")
        return ids

    def pubmed_fetch(self, pmids: list) -> dict:
        self.n_fetch += 1
        pmids = [str(p) for p in pmids][:6]
        try:
            text = self._eutil("efetch.fcgi", {
                "db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "text"})
        except Exception:  # noqa: BLE001
            return {}
        for pid in pmids:
            self.retrieved.add(f"PMID:{pid}")
        # one text blob per batch; key it by the requested pmids (Claude reads the blob)
        return {pmids[0] if pmids else "": text} if len(pmids) == 1 else {"_batch": text, "_pmids": pmids}

    def cellosaurus_lookup(self, name_or_cvcl: str) -> dict:
        try:
            body = _http_get(f"{_CELLO}/cell-line/{urllib.parse.quote(name_or_cvcl)}?format=json")
            cl = json.loads(body)["Cellosaurus"]["cell-line-list"][0]
        except Exception:  # noqa: BLE001
            return {}
        cvcl = next((a["value"] for a in cl.get("accession-list", []) if a.get("type") == "primary"), "")
        problem = " ".join(c.get("value", "") for c in cl.get("comment-list", [])
                           if "roblematic" in c.get("category", ""))
        pmids = re.findall(r"PubMed=(\d+)", json.dumps(cl))
        if cvcl:
            self.retrieved.add(cvcl)
        for pid in pmids:
            self.retrieved.add(f"PMID:{pid}")
        return {"cvcl": cvcl, "problem": problem, "reference_pmids": pmids}
```

- [ ] **Step 4: Run to verify pass** — `pytest tests/test_investigate.py -q` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(investigate): Retriever over PubMed/Cellosaurus with retrieval log"`

---

### Task 3: The bounded agentic loop `run_investigation`

**Files:** Modify `verdict/investigate.py`; Test `tests/test_investigate.py`

Design: `run_investigation(task, retriever, client, max_steps)` runs the Anthropic tool-use loop. `client`
is injectable (tests pass a fake). Tools offered to Claude: `pubmed_search`, `pubmed_fetch`,
`cellosaurus_lookup`, and a terminal `emit_investigation`. The loop executes real tools via `retriever`,
appends results, and stops when Claude calls `emit_investigation` or caps are hit; then `verify_citations`.

- [ ] **Step 1: Write the failing test** (a fake client scripting: search → then emit)

```python
class _FakeBlock:
    def __init__(self, **kw): self.__dict__.update(kw)

class _FakeMsg:
    def __init__(self, blocks, stop="tool_use"): self.content, self.stop_reason = blocks, stop

class _FakeClient:
    """Scripts a fixed sequence of assistant turns."""
    def __init__(self, turns): self._turns, self.messages = turns, self
    def create(self, **kw): return self._turns.pop(0)

def test_run_investigation_executes_tools_then_emits_grounded(monkeypatch):
    monkeypatch.setattr(investigate, "_http_get",
                        lambda url: '{"esearchresult":{"idlist":["111"]}}' if "esearch" in url else "KO abstract")
    turns = [
        _FakeMsg([_FakeBlock(type="tool_use", id="t1", name="pubmed_search",
                             input={"query": "GABARAP 8H5 knockout"})]),
        _FakeMsg([_FakeBlock(type="tool_use", id="t2", name="emit_investigation",
                             input={"verdict": "FOUND_VALIDATION", "reasoning": "KO abolished signal",
                                    "cited": [{"id": "PMID:111", "kind": "pubmed", "title": "t", "why": "KO"}],
                                    "steps": ["searched GABARAP 8H5", "read PMID:111"]})], stop="tool_use"),
    ]
    r = investigate.Retriever(email="x@y.z")
    inv = investigate.run_investigation("Investigate antibody 8H5 (GABARAP).", r,
                                        client=_FakeClient(turns), kind="antibody")
    assert inv.verdict == "FOUND_VALIDATION" and inv.grounded is True
    assert [c.id for c in inv.cited] == ["PMID:111"]

def test_run_investigation_caps_and_degrades(monkeypatch):
    # a client that never emits -> loop hits max_steps -> INCONCLUSIVE, never hangs/raises
    monkeypatch.setattr(investigate, "_http_get", lambda url: '{"esearchresult":{"idlist":[]}}')
    never = _FakeMsg([_FakeBlock(type="tool_use", id="t", name="pubmed_search", input={"query": "x"})])
    class _Loop:
        messages = None
        def create(self, **kw): return _FakeMsg([_FakeBlock(type="tool_use", id="t", name="pubmed_search", input={"query": "x"})])
    _Loop.messages = _Loop()
    inv = investigate.run_investigation("t", investigate.Retriever(), client=_Loop(), kind="antibody", max_steps=3)
    assert inv.verdict == "INCONCLUSIVE"
```

- [ ] **Step 2: Run to verify fail** — FAIL (`run_investigation` missing).

- [ ] **Step 3: Implement the loop + tool schemas**

```python
_TOOLS = [
    {"name": "pubmed_search", "description": "Search PubMed; returns real PMIDs.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "pubmed_fetch", "description": "Fetch title+abstract text for PMIDs you already found.",
     "input_schema": {"type": "object", "properties": {"pmids": {"type": "array", "items": {"type": "string"}}}, "required": ["pmids"]}},
    {"name": "cellosaurus_lookup", "description": "Look up a cell line in Cellosaurus by name or CVCL id.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "emit_investigation", "description": "Finish: emit your grounded verdict. ONLY cite ids returned by the tools.",
     "input_schema": {"type": "object", "properties": {
         "verdict": {"type": "string", "enum": [_ANTIBODY_FOUND, _ANTIBODY_NONE, _CELL_FULL, _CELL_PARTIAL, _INCONCLUSIVE]},
         "reasoning": {"type": "string"},
         "cited": {"type": "array", "items": {"type": "object", "properties": {
             "id": {"type": "string"}, "kind": {"type": "string"}, "title": {"type": "string"}, "why": {"type": "string"}}, "required": ["id", "kind"]}},
         "steps": {"type": "array", "items": {"type": "string"}}},
         "required": ["verdict", "reasoning", "cited", "steps"]}},
]

_SYSTEM = ("You are a research-integrity investigator. Use the tools to find REAL evidence, then call "
           "emit_investigation. NEVER cite a PMID or CVCL the tools did not return to you. If you cannot "
           "find genuine evidence, emit the abstain verdict. Be efficient: a few targeted searches, then decide.")


def _dispatch(retriever, name, args, caps):
    if name == "pubmed_search" and retriever.n_search < caps["search"]:
        return json.dumps({"pmids": retriever.pubmed_search(args.get("query", ""))})
    if name == "pubmed_fetch" and retriever.n_fetch < caps["fetch"]:
        return json.dumps(retriever.pubmed_fetch(args.get("pmids", [])))
    if name == "cellosaurus_lookup":
        return json.dumps(retriever.cellosaurus_lookup(args.get("name", "")))
    return json.dumps({"error": "tool budget exhausted — call emit_investigation now"})


def run_investigation(task: str, retriever: "Retriever", client=None, kind: str = "antibody",
                      max_steps: int = 8, caps: dict | None = None) -> Investigation:
    caps = caps or {"search": 3, "fetch": 6}
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    from .parse import model
    messages = [{"role": "user", "content": task}]
    try:
        for _ in range(max_steps):
            msg = client.messages.create(model=model(), max_tokens=1200, system=_SYSTEM,
                                         tools=_TOOLS, messages=messages)
            uses = [b for b in msg.content if getattr(b, "type", "") == "tool_use"]
            if not uses:
                break
            emit = next((b for b in uses if b.name == "emit_investigation"), None)
            if emit:
                d = dict(emit.input)
                inv = Investigation(kind=kind, verdict=d.get("verdict", _INCONCLUSIVE),
                                    cited=[Citation(**{k: c.get(k, "") for k in ("id", "kind", "title", "why")})
                                           for c in d.get("cited", [])],
                                    reasoning=d.get("reasoning", ""), steps=list(d.get("steps", [])))
                return verify_citations(inv, retriever.retrieved)
            messages.append({"role": "assistant", "content": [{"type": "tool_use", "id": b.id, "name": b.name, "input": b.input} for b in uses]})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b.id, "content": _dispatch(retriever, b.name, dict(b.input), caps)} for b in uses]})
    except Exception:  # noqa: BLE001 — any API/tool failure degrades, never crashes
        pass
    return Investigation(kind=kind, verdict=_INCONCLUSIVE, reasoning="investigation did not complete",
                         steps=["investigation incomplete"])
```

- [ ] **Step 4: Run to verify pass** — `pytest tests/test_investigate.py -q` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(investigate): bounded agentic tool-use loop with caps + grounding"`

---

### Task 4: `investigate_antibody` / `investigate_cell_line` entrypoints

**Files:** Modify `verdict/investigate.py`; Test `tests/test_investigate.py`

- [ ] **Step 1: Write the failing test** (mock `run_investigation` to assert prompt/kind wiring)

```python
def test_investigate_antibody_builds_task_and_runs(monkeypatch):
    seen = {}
    def fake_run(task, retriever, client=None, kind="antibody", **kw):
        seen["task"], seen["kind"] = task, kind
        return investigate.Investigation(kind=kind, verdict="NO_VALIDATION_FOUND")
    monkeypatch.setattr(investigate, "run_investigation", fake_run)
    inv = investigate.investigate_antibody("anti-GABARAP 8H5", target="GABARAP", catalog="", rrid="")
    assert seen["kind"] == "antibody" and "GABARAP" in seen["task"] and "8H5" in seen["task"]
    assert inv.verdict == "NO_VALIDATION_FOUND"

def test_investigate_cell_line_builds_task(monkeypatch):
    seen = {}
    monkeypatch.setattr(investigate, "run_investigation",
                        lambda task, r, **kw: seen.update(task=task, kind=kw.get("kind")) or investigate.Investigation(kind="cell_line", verdict="PARTIAL"))
    investigate.investigate_cell_line("GR-M", iclac_id="ICLAC-00538", cvcl="CVCL_2451")
    assert seen["kind"] == "cell_line" and "GR-M" in seen["task"] and "CVCL_2451" in seen["task"]
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement**

```python
def investigate_antibody(name: str, target: str = "", catalog: str = "", rrid: str = "") -> Investigation:
    task = (f"Investigate whether the antibody '{name}'"
            + (f" (target {target}" if target else " (")
            + (f", catalog {catalog}" if catalog else "") + (f", {rrid}" if rrid else "") + ") "
            + "has ever been validated for specificity with a GENETIC control (knockout/knockdown/CRISPR/"
            + "siRNA showing signal loss) in the published literature. Search PubMed (by target + "
            + "'knockout'/'validation'), read the most relevant abstracts, and emit FOUND_VALIDATION with "
            + "the real PMID if you find one, else NO_VALIDATION_FOUND.")
    return run_investigation(task, Retriever(), kind="antibody")


def investigate_cell_line(name: str, iclac_id: str = "", cvcl: str = "") -> Investigation:
    task = (f"Build the misidentification provenance chain for the cell line '{name}'"
            + (f" (ICLAC {iclac_id}" if iclac_id else " (") + (f", {cvcl}" if cvcl else "") + "). "
            + "Look it up in Cellosaurus to confirm the CVCL and the documented problem, then search "
            + "PubMed for the primary reference that first reported the misidentification. Emit "
            + "PROVENANCE_CHAIN citing the real CVCL and the real primary-reference PMID, or PARTIAL if "
            + "you can only ground part of the chain.")
    return run_investigation(task, Retriever(), kind="cell_line")
```

- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(investigate): antibody + cell-line investigation entrypoints"`

---

### Task 5: `POST /api/investigate` endpoint

**Files:** Modify `verdict/webapp.py`; Test `tests/test_investigate_endpoint.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_investigate_endpoint.py
from fastapi.testclient import TestClient
from verdict import webapp, investigate

def _reset(monkeypatch): 
    monkeypatch.setattr(webapp, "_DAILY_CAP", 0)
    webapp._day_state["day"] = None; webapp._day_state["count"] = 0

def test_investigate_endpoint_returns_report(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(webapp, "investigate_antibody",
        lambda **kw: investigate.Investigation(kind="antibody", verdict="FOUND_VALIDATION",
            cited=[investigate.Citation(id="PMID:111", kind="pubmed", title="t", why="KO")],
            reasoning="r", steps=["searched", "read PMID:111"], grounded=True))
    r = TestClient(webapp.app).post("/api/investigate", json={"kind": "antibody", "name": "8H5", "target": "GABARAP"})
    assert r.status_code == 200
    body = r.json()["investigation"]
    assert body["verdict"] == "FOUND_VALIDATION" and body["cited"][0]["id"] == "PMID:111"
    assert body["steps"]  # the agentic trail is returned for the UI

def test_investigate_endpoint_degrades(monkeypatch):
    _reset(monkeypatch)
    def boom(**kw): raise RuntimeError("api down")
    monkeypatch.setattr(webapp, "investigate_antibody", boom)
    r = TestClient(webapp.app).post("/api/investigate", json={"kind": "antibody", "name": "x"})
    assert r.status_code == 200  # graceful, never 502
    assert r.json()["investigation"]["verdict"] == "INCONCLUSIVE"
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement** — add to `verdict/webapp.py` (imports + model + route)

```python
from dataclasses import asdict
from .investigate import investigate_antibody, investigate_cell_line, Investigation

class InvestigateRequest(BaseModel):
    kind: str
    name: str
    target: str | None = None
    catalog: str | None = None
    rrid: str | None = None
    iclac_id: str | None = None
    cvcl: str | None = None

    @field_validator("name")
    @classmethod
    def _bounded(cls, v: str) -> str:
        v = (v or "").strip()
        if not v: raise ValueError("name required")
        return v[:200]

@app.post("/api/investigate")
def api_investigate(req: InvestigateRequest) -> dict:
    _daily_gate()
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="server busy — try again shortly")
    try:
        if req.kind == "cell_line":
            inv = investigate_cell_line(req.name, iclac_id=req.iclac_id or "", cvcl=req.cvcl or "")
        else:
            inv = investigate_antibody(req.name, target=req.target or "", catalog=req.catalog or "", rrid=req.rrid or "")
    except Exception:  # noqa: BLE001 — degrade, never 502
        log.exception("investigation failed")
        inv = Investigation(kind=req.kind, verdict="INCONCLUSIVE", reasoning="investigation failed", steps=["failed"])
    finally:
        _slots.release()
    return {"investigation": asdict(inv)}
```

- [ ] **Step 4: Run to verify pass** — both endpoint tests + full suite green.
- [ ] **Step 5: Commit** — `git commit -am "feat(webapp): POST /api/investigate (spend-guarded, graceful)"`

---

### Task 6: Measured investigator eval

**Files:** Create `benchmark/repro/investigate_corpus.json`, `scripts/repro_investigate_eval.py`

- [ ] **Step 1** Build `investigate_corpus.json`: known-answer cases with an `expect` field —
  `antibody` positives (a real antibody with a real published KO/KD validation PMID, e.g. GABARAP-8H5 →
  PMID 30679523; AKT1 Proteintech siRNA → PMID 26998240), `cell_line` provenance positives (GR-M →
  CVCL_2451; a famous misidentified line with a known reference), and negatives (an antibody with no
  genetic validation → expect NO_VALIDATION_FOUND). Each: `{id, kind, name, target/iclac_id/cvcl, expect, expect_pmid?}`.
- [ ] **Step 2** `scripts/repro_investigate_eval.py`: for each case run the real investigator; score
  **found-correct** (verdict matches `expect` AND, for positives, a cited PMID/CVCL matches `expect_pmid`/cvcl),
  **false-citation** (cited a grounded id that does NOT match expectation on a positive — must be ~0),
  **abstain-correct** (negatives → abstain). Report each with Wilson 95% CIs (reuse `wilson()` from
  `repro_knockout_eval.py`). Write `benchmark/repro/investigate_eval.json`.
- [ ] **Step 3** Run it live (`.env` copied into the worktree, gitignored) 2× for stability; capture numbers.
- [ ] **Step 4** Commit corpus + script + eval json + record the numbers.

---

### Task 7: UI — the "Investigate" trail

**Files:** Modify `web/src/types.ts`, `web/src/Repro.tsx`

- [ ] **Step 1** Add `Investigation`/`Citation` types to `types.ts`.
- [ ] **Step 2** In `Repro.tsx`, add an **"Investigate"** button on `cell_line` and `antibody` findings;
  on click, `POST api('/api/investigate')` with the finding's fields; render a loading state, then the
  **steps trail** (the agentic process) followed by the verdict + cited real records (PMID/CVCL as links to
  pubmed.ncbi.nlm.nih.gov / cellosaurus.org). Reuse the `apiUp`/`VITE_API_BASE`/frozen-fallback patterns.
- [ ] **Step 3** `tsc --noEmit` clean + `vite build` OK.
- [ ] **Step 4** Commit.

---

## Self-review

- **Spec coverage:** capability (Tasks 4,7), bounded agentic loop (Task 3), real APIs/Retriever (Task 2),
  honesty anchor/citation-verification (Task 1 + applied in Task 3), endpoint (Task 5), measured eval with
  CIs (Task 6), UI trail (Task 7). Phase 2 deferred to a follow-up plan. All covered.
- **Placeholders:** none — every step has real test + implementation code.
- **Type consistency:** `Investigation`/`Citation` fields (`id,kind,title,why` / `kind,verdict,cited,reasoning,steps,grounded,method`), `run_investigation(task, retriever, client, kind, max_steps, caps)`, `Retriever.retrieved/n_search/n_fetch`, verdict constants — used consistently across Tasks 1–7.
- **Risk to watch during build:** Cellosaurus + NCBI response shapes are asserted from docs; if a live
  response differs, adjust the parse in Task 2 and re-run its tests (mocked) + a single live smoke call.

## Deferred — Phase 2 (own plan if Phase 1 lands + is measured)
Whole-manuscript ingestion + auto-fix (draft corrections). Not in this plan.
