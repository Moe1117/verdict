"""Orchestration: claim -> verdict card.

parse -> retrieve -> extract -> integrity-screen -> deterministic gates -> calibrate.
The LLM touches parse and extract only; the verdict itself comes from gates.py.

`evaluate()` works on any list of rows. `run_frozen()` runs it over the frozen,
verified demo corpora (no network, no LLM) — the deterministic demo path.
"""
from __future__ import annotations

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


def run_live(claim: str, k: int = 8) -> VerdictCard:
    """The full live path: claim -> Claude parse -> PubMed retrieval -> Claude extraction
    -> deterministic gates. Requires ANTHROPIC_API_KEY (+ NCBI_EMAIL per NCBI policy).
    The LLM only parses the claim and extracts each study; the verdict is still a pure
    function of the extracted rows."""
    from .extract import extract_row
    from .parse import parse_claim
    from .retrieve import fetch_abstract, retraction_note, search_pubmed

    ct, query = parse_claim(claim)
    if not ct.measurable:
        return VerdictCard(
            claim=claim, verdict=Verdict.UNDECIDABLE, confidence=None, ledger=[],
            gate_trace=[GateTrace("input-guard", False,
                                  "claim is ill-posed or its outcome is not objectively measurable")],
        )
    rows: list[EvidenceRow] = []
    seen: set[str] = set()
    for s in search_pubmed(query, retmax=k):
        if s.id in seen:
            continue
        seen.add(s.id)
        try:
            row = extract_row(s, fetch_abstract(s.id), ct)
        except Exception:  # noqa: BLE001 — one bad study never sinks the run
            continue
        # Deterministic integrity override: if the source database itself flags the study as
        # retracted / under an expression of concern, it is inert regardless of what the LLM
        # extractor concluded. Retraction is a citable fact, never an LLM judgement.
        if s.integrity_severity:
            row.integrity_ok = False
            row.integrity_note = retraction_note(s)
        rows.append(row)
    return evaluate(claim, rows)
