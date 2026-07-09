"""run_live accepts an optional on_event callback that reports pipeline progress — parse, each
retrieval, each extracted study, then the gate step — so a UI can stream the resolution as it
happens. The callback is purely additive: run_live's verdict is unchanged whether or not it is
passed. Proven with the two Claude calls + network mocked, so no API key is needed."""
from verdict import extract, parse, retrieve
from verdict import verdict as vmod
from verdict.gates import EvidenceRow, Verdict
from verdict.parse import ClaimTuple
from verdict.retrieve import Source


def _src(pid):
    return Source(kind="pubmed", id=pid, title=f"Study {pid}", authors="A", journal="J", year="2020", url="u")


def test_run_live_emits_progress_events(monkeypatch):
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "drugX mortality"))
    monkeypatch.setattr(retrieve, "search_pubmed", lambda q, retmax=8: [_src("PMID:1"), _src("PMID:2")])
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: "transient abstract")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [])
    rows = {
        "PMID:1": EvidenceRow(citation="c", source_id="PMID:1", design="meta-analysis of rcts",
                              direction=1, population_match=True, finding="pooled benefit"),
        "PMID:2": EvidenceRow(citation="c", source_id="PMID:2", design="rct", direction=1,
                              population_match=True, n_int=5000, finding="rct benefit"),
    }
    monkeypatch.setattr(extract, "extract_row", lambda s, a, c: rows[s.id])

    events = []
    card = vmod.run_live("drugX improves survival in adults", on_event=events.append)

    stages = [e["stage"] for e in events]
    assert stages[0] == "parse"
    assert events[0]["measurable"] is True and events[0]["query"] == "drugX mortality"
    assert "search" in stages                     # at least the PubMed search reported
    study = [e for e in events if e["stage"] == "study"]
    assert {e["source_id"] for e in study} == {"PMID:1", "PMID:2"}  # one per committed row
    assert study[0]["design"] and "direction" in study[0] and "integrity_ok" in study[0]
    assert stages[-1] == "gate"                    # the deterministic verdict step is last
    assert card.verdict is Verdict.SUPPORTED       # additive: the verdict is unchanged
    assert len(card.ledger) == 2


def test_run_live_events_stop_at_guard_when_unmeasurable(monkeypatch):
    ct = ClaimTuple(raw="x", agent="?", outcome="vibes", population="?", direction=1, measurable=False)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, ""))
    events = []
    card = vmod.run_live("does this vibe well", on_event=events.append)
    assert card.verdict is Verdict.UNDECIDABLE
    assert events and events[0]["stage"] == "parse" and events[0]["measurable"] is False


def test_run_live_aborts_when_should_abort_is_set(monkeypatch):
    """A cooperative should_abort() lets a disconnected SSE client stop the ~40s of paid work.
    When it is already set, run_live extracts nothing and returns immediately."""
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "q"))
    monkeypatch.setattr(retrieve, "search_pubmed", lambda q, retmax=8: [_src("PMID:1"), _src("PMID:2")])
    extracted: list = []
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: extracted.append(pid) or "abstract")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [])
    monkeypatch.setattr(extract, "extract_row", lambda s, a, c:
                        EvidenceRow(citation="c", source_id=s.id, design="rct", direction=1, population_match=True))
    card = vmod.run_live("drugX improves survival", should_abort=lambda: True)
    assert card.ledger == [] and extracted == []  # no fetch, no extraction once aborted


def test_run_live_still_works_without_callback(monkeypatch):
    """Backward compatibility: the callback defaults to off and nothing changes."""
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "q"))
    monkeypatch.setattr(retrieve, "search_pubmed", lambda q, retmax=8: [_src("PMID:1")])
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: "abstract")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [])
    monkeypatch.setattr(extract, "extract_row", lambda s, a, c:
                        EvidenceRow(citation="c", source_id=s.id, design="rct", direction=1,
                                    population_match=True, n_int=5000))
    card = vmod.run_live("drugX improves survival")
    assert len(card.ledger) == 1
