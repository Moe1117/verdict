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
    assert "gate" in stages                        # the deterministic verdict step is emitted
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


def _disconfirming(q):
    return any(w in q.lower() for w in ("no effect", "did not", "failed", "no benefit",
                                        "nonsignificant", "improved", "reduced", "benefit", "efficacy"))


def test_run_live_falsification_flips_supported_when_disconfirming_evidence_surfaces(monkeypatch):
    """A first-pass Supported that rested on incomplete retrieval must not stand: the falsification
    pass runs a disconfirming search, a large contradicting RCT surfaces, and the gate re-decides."""
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "drugX mortality"))
    main = [_src("PMID:1"), _src("PMID:2")]        # first pass: two large positive RCTs -> Supported
    disc = [_src("PMID:3")]                          # disconfirming pass: a large negative RCT

    def fake_search(q, retmax=8):
        return disc if _disconfirming(q) else main
    monkeypatch.setattr(retrieve, "search_pubmed", fake_search)
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: "abstract")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [])
    rows = {
        "PMID:1": EvidenceRow(citation="c", source_id="PMID:1", design="rct", direction=1, population_match=True, n_int=5000),
        "PMID:2": EvidenceRow(citation="c", source_id="PMID:2", design="rct", direction=1, population_match=True, n_int=6000),
        "PMID:3": EvidenceRow(citation="c", source_id="PMID:3", design="rct", direction=-1, population_match=True, n_int=8000),
    }
    monkeypatch.setattr(extract, "extract_row", lambda s, a, c: rows[s.id])

    events = []
    card = vmod.run_live("drugX reduces mortality in adults", on_event=events.append)
    assert any(e["stage"] == "disconfirm" for e in events)                 # it tried to refute itself
    assert card.verdict is Verdict.CONTESTED                                # 2 large pos vs 1 large neg
    assert {r.source_id for r in card.ledger} == {"PMID:1", "PMID:2", "PMID:3"}


def test_run_live_verdict_holds_when_no_disconfirming_evidence(monkeypatch):
    """When a genuine disconfirming search comes back empty, the decided verdict stands."""
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "drugX mortality"))

    def fake_search(q, retmax=8):
        return [] if _disconfirming(q) else [_src("PMID:1"), _src("PMID:2")]
    monkeypatch.setattr(retrieve, "search_pubmed", fake_search)
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: "abstract")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [])
    monkeypatch.setattr(extract, "extract_row", lambda s, a, c:
                        EvidenceRow(citation="c", source_id=s.id, design="rct", direction=1,
                                    population_match=True, n_int=5000))
    card = vmod.run_live("drugX reduces mortality in adults")
    assert card.verdict is Verdict.SUPPORTED                                # survived the refutation attempt


def test_falsification_pass_can_be_disabled_via_env(monkeypatch):
    """VERDICT_FALSIFY=0 turns the falsification pass off (fast mode / A/B baseline): a decided
    verdict is returned without a disconfirming search."""
    monkeypatch.setenv("VERDICT_FALSIFY", "0")
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "drugX mortality"))

    def fake_search(q, retmax=8):
        return [_src("PMID:3")] if _disconfirming(q) else [_src("PMID:1"), _src("PMID:2")]
    monkeypatch.setattr(retrieve, "search_pubmed", fake_search)
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: "abstract")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [])
    monkeypatch.setattr(extract, "extract_row", lambda s, a, c:
                        EvidenceRow(citation="c", source_id=s.id, design="rct", direction=1,
                                    population_match=True, n_int=5000))
    events = []
    card = vmod.run_live("drugX reduces mortality", on_event=events.append)
    assert not any(e["stage"] == "disconfirm" for e in events)
    assert card.verdict is Verdict.SUPPORTED   # PMID:3 (the disconfirming negative) never retrieved


def test_run_live_no_falsification_pass_for_an_abstention(monkeypatch):
    """An abstention (Insufficient) is already withholding — no disconfirming pass runs."""
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "q"))
    monkeypatch.setattr(retrieve, "search_pubmed", lambda q, retmax=8: [_src("PMID:1")])
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: "abstract")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [])
    monkeypatch.setattr(extract, "extract_row", lambda s, a, c:
                        EvidenceRow(citation="c", source_id=s.id, design="preclinical", direction=1, population_match=True))
    events = []
    card = vmod.run_live("drugX reduces mortality", on_event=events.append)
    assert card.verdict is Verdict.INSUFFICIENT
    assert not any(e["stage"] == "disconfirm" for e in events)


def test_parallel_extraction_isolates_a_failing_study(monkeypatch):
    """Studies are fetched + extracted concurrently; one study whose extraction raises must not
    sink the others, and the full set still resolves (order-independent)."""
    ct = ClaimTuple(raw="x", agent="drugX", outcome="mortality", population="adults", direction=-1)
    monkeypatch.setattr(parse, "parse_claim", lambda c: (ct, "q"))
    srcs = [_src("PMID:1"), _src("PMID:2"), _src("PMID:3")]
    monkeypatch.setattr(retrieve, "search_pubmed", lambda q, retmax=8: [] if _disconfirming(q) else srcs)
    monkeypatch.setattr(retrieve, "fetch_abstract", lambda pid: "abstract")
    monkeypatch.setattr(retrieve, "search_trials", lambda q, page_size=8: [])

    def flaky_extract(s, a, c):
        if s.id == "PMID:2":
            raise RuntimeError("boom")
        return EvidenceRow(citation="c", source_id=s.id, design="rct", direction=1,
                           population_match=True, n_int=5000)
    monkeypatch.setattr(extract, "extract_row", flaky_extract)

    card = vmod.run_live("drugX reduces mortality in adults")
    assert {r.source_id for r in card.ledger} == {"PMID:1", "PMID:3"}  # failing PMID:2 dropped, run survived


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
