"""Orchestration: claim -> verdict card.

parse -> retrieve -> extract -> integrity-screen -> deterministic gates -> calibrate.
The LLM touches parse and extract only; the verdict itself comes from gates.py.

`evaluate()` works on any list of rows. `run_frozen()` runs it over the frozen,
verified demo corpora (no network, no LLM) — the deterministic demo path.
"""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import DISCLAIMER
from .gates import EvidenceRow, GateTrace, Verdict, resolve


@dataclass
class VerdictCard:
    claim: str
    verdict: Verdict
    confidence: float | None
    ledger: list[EvidenceRow]
    gate_trace: list[GateTrace]
    what_would_change_it: str = ""
    disclaimer: str = DISCLAIMER


def evaluate(claim: str, rows: list[EvidenceRow], confidence: float | None = None) -> VerdictCard:
    """Given extracted evidence rows, produce the auditable verdict card."""
    from .directive import research_directive

    verdict, trace = resolve(rows)
    return VerdictCard(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        ledger=rows,
        gate_trace=trace,
        what_would_change_it=research_directive(verdict, trace),
    )


def run_frozen(claim_id: str) -> VerdictCard:
    """Resolve a claim from the frozen demo corpora (deterministic, offline)."""
    from .corpora import load_rows

    meta, rows = load_rows(claim_id)
    return evaluate(meta.get("claim", claim_id), rows)


def run_live(claim: str, k: int = 8, on_event: Callable[[dict], None] | None = None,
             should_abort: Callable[[], bool] | None = None) -> VerdictCard:
    """The full live path: claim -> Claude parse -> PubMed retrieval -> Claude extraction
    -> deterministic gates. Requires ANTHROPIC_API_KEY (+ NCBI_EMAIL per NCBI policy).
    The LLM only parses the claim and extracts each study; the verdict is still a pure
    function of the extracted rows.

    `on_event`, if given, is called with a small dict at each pipeline milestone (parse, each
    retrieval, each extracted study, the gate step) so a UI can stream the resolution live. It is
    purely observational: the returned verdict is identical whether or not it is passed.

    `should_abort`, if given, is polled before each expensive step; when it returns True the run
    stops early (e.g. the SSE client disconnected) and resolves whatever was gathered so far,
    rather than continuing ~40s of paid Claude + retrieval calls no one is waiting for."""
    from .extract import extract_row
    from .parse import parse_claim
    from .retrieve import fetch_abstract, fetch_trial, retraction_note, search_pubmed, search_trials

    def emit(**event) -> None:
        if on_event is not None:
            on_event(event)

    def aborted() -> bool:
        return should_abort is not None and should_abort()

    ct, query = parse_claim(claim)
    emit(stage="parse", measurable=bool(ct.measurable), query=query)
    if not ct.measurable:
        from .directive import research_directive
        guard = [GateTrace("input-guard", False,
                           "claim is ill-posed or its outcome is not objectively measurable")]
        return VerdictCard(
            claim=claim, verdict=Verdict.UNDECIDABLE, confidence=None, ledger=[],
            gate_trace=guard, what_would_change_it=research_directive(Verdict.UNDECIDABLE, guard),
        )
    rows: list[EvidenceRow] = []
    seen: set[str] = set()
    lock = threading.Lock()
    # Each study's fetch + Claude extraction is independent and I/O-bound, so they run concurrently
    # (threads release the GIL on network I/O). Bounded to stay polite to NCBI / the Anthropic API.
    workers = max(1, int(os.getenv("VERDICT_CONCURRENCY", "6")))

    def commit(s, text: str | None) -> None:
        if not text:
            return
        with lock:  # dedup atomically so two passes never extract the same source twice
            if s.id in seen:
                return
            seen.add(s.id)
        try:
            row = extract_row(s, text, ct)  # the slow Claude call — deliberately OUTSIDE the lock
        except Exception:  # noqa: BLE001 — one bad study never sinks the run
            return
        # Deterministic integrity override: if the source database itself flags the study as
        # retracted / under an expression of concern, it is inert regardless of what the LLM
        # extractor concluded. Retraction is a citable fact, never an LLM judgement.
        if s.integrity_severity:
            row.integrity_ok = False
            row.integrity_note = retraction_note(s)
        with lock:  # shared-state mutation + emit serialized (on_event need not be thread-safe)
            rows.append(row)
            emit(stage="study", source_id=row.source_id or s.id, design=row.design,
                 direction=row.direction, integrity_ok=row.integrity_ok, finding=row.finding)

    def _fetch_commit(s, fetch) -> None:
        if aborted():
            return
        try:
            text = fetch(s)
        except Exception:  # noqa: BLE001
            return
        commit(s, text)

    def gather(sources, fetch) -> None:
        """Fetch + extract every source concurrently (verdict is order-independent)."""
        if not sources:
            return
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(lambda s: _fetch_commit(s, fetch), sources))

    if aborted():
        return evaluate(claim, rows)
    pubmed = search_pubmed(query, retmax=k)
    emit(stage="search", source="pubmed", found=len(pubmed))
    gather(pubmed, lambda s: fetch_abstract(s.id))
    if aborted():
        return evaluate(claim, rows)
    # ClinicalTrials.gov: add trials with POSTED RESULTS (orthogonal recall — the definitive
    # trials a PubMed query can miss). Registrations without results are skipped (not evidence).
    try:
        trials = search_trials(query, page_size=k)
    except Exception:  # noqa: BLE001 — CT.gov being unavailable never sinks the run
        trials = []
    emit(stage="search", source="clinicaltrials", found=len(trials))
    gather(trials, lambda s: fetch_trial(s.id))
    emit(stage="gate", n=len(rows))
    card = evaluate(claim, rows)

    # Falsification pass — before committing a DECIDED verdict, actively look for the evidence that
    # would contradict it. The engine is never confidently wrong on a complete evidence set; the
    # live risk is an INCOMPLETE set (a query that missed the pivotal negative trial). So we run a
    # second, disconfirming retrieval and let the deterministic gate re-decide over the union. A
    # verdict that survives is trustworthy; a missed contradiction gets its chance to flip it
    # (usually -> Contested / Insufficient). Still no LLM in the verdict path.
    if not aborted() and os.getenv("VERDICT_FALSIFY", "1") != "0":
        from .disconfirm import disconfirming_query
        dq = disconfirming_query(ct, card.verdict)
        if dq:
            emit(stage="disconfirm", query=dq)
            before = len(rows)
            # A focused pass: PubMed relevance-sorts, so the top few disconfirming hits carry the
            # pivotal contradiction. Capped to keep the extra latency bounded; extracted in parallel.
            try:
                disc = search_pubmed(dq, retmax=min(k, 5))
            except Exception:  # noqa: BLE001 — a failed disconfirming search never sinks the run
                disc = []
            gather(disc, lambda s: fetch_abstract(s.id))
            if len(rows) > before:
                card = evaluate(claim, rows)
            emit(stage="disconfirm_done", added=len(rows) - before, verdict=card.verdict.value)
    return card
