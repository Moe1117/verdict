"""Phase 2 — whole-manuscript ingestion + auto-fix (verdict/manuscript.py).

Ingest a full Methods/manuscript (chunk if long), extract EVERY resource, dedupe across chunks, run the
same deterministic gates, optionally run the agentic investigator on flagged resources, and optionally
draft submission-ready corrections. Every correction is a LABELLED draft — the honesty discipline that
keeps /api/repro's headline rule-only extends here: auto-fix never fabricates an identity.
"""
from verdict import investigate, manuscript, repro
from verdict.investigate import Investigation
from verdict.manuscript import Correction, ManuscriptReport


# ---- chunking -------------------------------------------------------------------------------------

def test_chunk_text_single_chunk_when_short():
    assert manuscript._chunk_text("short methods text") == ["short methods text"]


def test_chunk_text_splits_long_text_with_overlap():
    text = "".join(f"S{i:04d}." for i in range(3000))          # ~18k chars
    chunks = manuscript._chunk_text(text, size=6000, overlap=300)
    assert len(chunks) > 1
    assert all(len(c) <= 6000 for c in chunks)
    assert "".join(chunks).__len__() >= len(text)               # overlapping cover, nothing dropped
    # overlap: the tail of chunk 0 reappears at the head of chunk 1
    assert chunks[0][-100:] in chunks[1] or chunks[1].startswith(chunks[0][6000 - 300:6000])


# ---- resource merge / dedupe ----------------------------------------------------------------------

def test_merge_resources_dedupes_cell_lines_and_antibodies():
    parts = [
        {"cell_lines": [{"name": "HeLa"}], "antibodies": [{"name": "anti-X", "catalog": "ab1"}], "rigor": {}},
        {"cell_lines": [{"name": "HeLa "}, {"name": "GR-M"}],                       # 'HeLa ' dupes HeLa
         "antibodies": [{"name": "anti-X", "catalog": "ab1"}, {"name": "anti-Y", "catalog": "ab2"}], "rigor": {}},
    ]
    merged = manuscript._merge_resources(parts)
    assert [c["name"].strip() for c in merged["cell_lines"]] == ["HeLa", "GR-M"]
    assert sorted(a["name"] for a in merged["antibodies"]) == ["anti-X", "anti-Y"]


def test_merge_resources_rigor_true_wins_over_false_and_null():
    parts = [
        {"cell_lines": [], "antibodies": [], "rigor": {"sex_reported": None, "blinding_stated": False}},
        {"cell_lines": [], "antibodies": [], "rigor": {"sex_reported": True, "blinding_stated": None}},
    ]
    rigor = manuscript._merge_resources(parts)["rigor"]
    assert rigor["sex_reported"] is True          # a True anywhere means it was reported somewhere
    assert rigor["blinding_stated"] is False       # False (explicitly omitted) beats null, no True seen


# ---- whole-manuscript review ----------------------------------------------------------------------

def test_review_manuscript_extracts_per_chunk_and_gates_merged(monkeypatch):
    from verdict import knockout
    monkeypatch.setattr(knockout, "call_tool",
                        lambda *a, **k: {"status": "not_reported", "evidence": "", "reasoning": "x"})
    long_text = "GR-M cells were used. " * 500                  # forces >1 chunk
    seen = {"n": 0}
    def fake_extract(chunk):
        seen["n"] += 1
        return {"cell_lines": [{"name": "GR-M", "evidence": "GR-M cells"}], "antibodies": [], "rigor": {}}
    mr = manuscript.review_manuscript(long_text, extract_fn=fake_extract)
    assert seen["n"] == mr.n_chunks and mr.n_chunks > 1          # extraction ran once per chunk
    assert mr.n_resources == 1                                    # GR-M deduped across chunks
    assert mr.report.verdict == "Needs fixes"                     # merged GR-M FAILs the register
    assert mr.investigations == [] and mr.corrections == []       # neither requested


def test_review_manuscript_runs_investigations_only_when_requested(monkeypatch):
    from verdict import knockout
    monkeypatch.setattr(knockout, "call_tool",
                        lambda *a, **k: {"status": "not_reported", "evidence": "", "reasoning": "x"})
    called = {"cell": []}
    monkeypatch.setattr(investigate, "investigate_cell_line",
                        lambda name, **k: called["cell"].append(name) or
                        Investigation(kind="cell_line", verdict="PROVENANCE_CHAIN", grounded=True))
    res = {"cell_lines": [{"name": "GR-M", "evidence": "GR-M cells"}], "antibodies": [], "rigor": {}}
    monkeypatch.setattr(repro, "extract_resources", lambda t: res)

    off = manuscript.review_manuscript("GR-M cells.", investigate=False)
    assert off.investigations == [] and called["cell"] == []

    on = manuscript.review_manuscript("GR-M cells.", investigate=True)
    assert called["cell"] == ["GR-M"]                             # flagged line was investigated
    assert on.investigations and on.investigations[0].verdict == "PROVENANCE_CHAIN"


def test_review_manuscript_bounds_investigation_count(monkeypatch):
    from verdict import knockout
    monkeypatch.setattr(knockout, "call_tool",
                        lambda *a, **k: {"status": "not_reported", "evidence": "", "reasoning": "x"})
    n = {"c": 0}
    monkeypatch.setattr(investigate, "investigate_cell_line",
                        lambda name, **k: (n.__setitem__("c", n["c"] + 1),
                                           Investigation(kind="cell_line", verdict="PARTIAL"))[1])
    res = {"cell_lines": [{"name": x} for x in ("GR-M", "KB", "FL", "HEp-2", "SNB-19")],
           "antibodies": [], "rigor": {}}                          # 5 flagged lines
    monkeypatch.setattr(repro, "extract_resources", lambda t: res)
    mr = manuscript.review_manuscript("x", investigate=True, max_investigations=2)
    assert n["c"] == 2 and len(mr.investigations) == 2             # capped, not one-per-flag


# ---- auto-fix (draft corrections) -----------------------------------------------------------------

def test_draft_corrections_only_for_actionable_findings(monkeypatch):
    captured = {}
    def fake_call(system, user, tool, **k):
        captured["user"] = user
        return {"corrections": [
            {"item": "cell line: GR-M", "suggestion": "STR-authenticate; GR-M is misidentified as <true id>.",
             "rationale": "on the ICLAC register"}]}
    monkeypatch.setattr(manuscript, "call_tool", fake_call)
    report = repro.ReproReport(findings=[
        repro.Finding("cell line: GR-M", "cell_line", "FAIL", "on register", "GR-M cells", "ICLAC-x · CVCL_y"),
        repro.Finding("cell line: HeLa", "cell_line", "PASS", "not on register", "HeLa cells")],
        verdict="Needs fixes", n_fail=1, n_pass=1, n_insufficient=0)
    out = manuscript.draft_corrections(report, "GR-M cells; HeLa cells.")
    assert [c.item for c in out] == ["cell line: GR-M"]            # PASS finding gets no correction
    assert isinstance(out[0], Correction) and out[0].original == "GR-M cells"
    assert out[0].label == "draft — human review required"        # never presented as authoritative
    assert "HeLa" not in captured["user"] or "GR-M" in captured["user"]  # only actionable findings sent


def test_draft_corrections_degrades_on_llm_error(monkeypatch):
    def boom(*a, **k): raise RuntimeError("api down")
    monkeypatch.setattr(manuscript, "call_tool", boom)
    report = repro.ReproReport(findings=[
        repro.Finding("cell line: GR-M", "cell_line", "FAIL", "on register", "GR-M cells", "ICLAC-x")],
        verdict="Needs fixes", n_fail=1, n_pass=0, n_insufficient=0)
    assert manuscript.draft_corrections(report, "GR-M cells.") == []   # never raises


def test_review_manuscript_autofix_populates_corrections(monkeypatch):
    from verdict import knockout
    monkeypatch.setattr(knockout, "call_tool",
                        lambda *a, **k: {"status": "not_reported", "evidence": "", "reasoning": "x"})
    monkeypatch.setattr(repro, "extract_resources",
                        lambda t: {"cell_lines": [{"name": "GR-M", "evidence": "GR-M cells"}],
                                   "antibodies": [], "rigor": {}})
    monkeypatch.setattr(manuscript, "call_tool", lambda s, u, tool, **k: {"corrections": [
        {"item": "cell line: GR-M", "suggestion": "STR-authenticate.", "rationale": "on register"}]})
    mr = manuscript.review_manuscript("GR-M cells.", autofix=True)
    assert len(mr.corrections) == 1 and mr.corrections[0].item == "cell line: GR-M"


# ---- serialization --------------------------------------------------------------------------------

def test_manuscript_report_to_dict_is_json_serializable():
    import json
    mr = ManuscriptReport(
        report=repro.ReproReport(findings=[repro.Finding("cell line: GR-M", "cell_line", "FAIL", "d")],
                                 verdict="Needs fixes", n_fail=1, n_pass=0, n_insufficient=0),
        investigations=[Investigation(kind="cell_line", verdict="PARTIAL")],
        corrections=[Correction("cell line: GR-M", "GR-M cells", "STR-authenticate.", "on register")],
        n_resources=1, n_chunks=2)
    d = manuscript.manuscript_report_to_dict(mr)
    s = json.dumps(d)                                              # must not raise
    assert d["n_chunks"] == 2 and d["report"]["verdict"] == "Needs fixes"
    assert d["corrections"][0]["label"] == "draft — human review required"
    assert d["investigations"][0]["verdict"] == "PARTIAL"
