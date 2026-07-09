"""Orchestration: claim -> verdict card.

parse -> retrieve -> extract -> integrity-screen -> deterministic gates -> calibrate.
The LLM touches parse and extract only; the verdict itself comes from gates.py.

`evaluate()` works on any list of rows. `run_frozen()` runs it over the frozen,
verified demo corpora (no network, no LLM) — the deterministic demo path.
"""
from __future__ import annotations

from collections.abc import Callable
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
    verdict, trace = resolve(rows)
    return VerdictCard(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        ledger=rows,
        gate_trace=trace,
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
        return VerdictCard(
            claim=claim, verdict=Verdict.UNDECIDABLE, confidence=None, ledger=[],
            gate_trace=[GateTrace("input-guard", False,
                                  "claim is ill-posed or its outcome is not objectively measurable")],
        )
    rows: list[EvidenceRow] = []
    seen: set[str] = set()

    def commit(s, text: str | None) -> None:
        if not text or s.id in seen:
            return
        seen.add(s.id)
        try:
            row = extract_row(s, text, ct)
        except Exception:  # noqa: BLE001 — one bad study never sinks the run
            return
        # Deterministic integrity override: if the source database itself flags the study as
        # retracted / under an expression of concern, it is inert regardless of what the LLM
        # extractor concluded. Retraction is a citable fact, never an LLM judgement.
        if s.integrity_severity:
            row.integrity_ok = False
            row.integrity_note = retraction_note(s)
        rows.append(row)
        emit(stage="study", source_id=row.source_id or s.id, design=row.design,
             direction=row.direction, integrity_ok=row.integrity_ok, finding=row.finding)

    if aborted():
        return evaluate(claim, rows)
    pubmed = search_pubmed(query, retmax=k)
    emit(stage="search", source="pubmed", found=len(pubmed))
    for s in pubmed:
        if aborted():
            return evaluate(claim, rows)
        try:
            abstract = fetch_abstract(s.id)
        except Exception:  # noqa: BLE001
            continue
        commit(s, abstract)
    if aborted():
        return evaluate(claim, rows)
    # ClinicalTrials.gov: add trials with POSTED RESULTS (orthogonal recall — the definitive
    # trials a PubMed query can miss). Registrations without results are skipped (not evidence).
    try:
        trials = search_trials(query, page_size=k)
    except Exception:  # noqa: BLE001 — CT.gov being unavailable never sinks the run
        trials = []
    emit(stage="search", source="clinicaltrials", found=len(trials))
    for s in trials:
        if aborted():
            return evaluate(claim, rows)
        try:
            commit(s, fetch_trial(s.id))
        except Exception:  # noqa: BLE001
            continue
    emit(stage="gate", n=len(rows))
    return evaluate(claim, rows)
