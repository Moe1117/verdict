"""Shared VerdictCard -> web Card JSON serializer.

Both the frozen deck (scripts/export_cards.py) and the live API (verdict/webapp.py) route through
this single function, so the two paths can never drift in shape or in how a card is derived. The
serialization is deterministic: certainty (GRADE profile), robustness, and the verdict-over-time
timeline are all pure functions of the same evidence rows the verdict rested on.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from .certainty import grade_certainty
from .robustness import robustness
from .timemachine import verdict_over_time
from .verdict import VerdictCard


def card_payload(
    card: VerdictCard,
    *,
    id: str,
    expected: str | None = None,
    baseline: dict | None = None,
    confidence_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Serialize a resolved VerdictCard into the web Card JSON shape.

    `expected` and `baseline` are corpus metadata that only the frozen deck carries; a live claim
    passes neither (they serialize to null). `confidence_map` maps a certainty level to its
    empirically-calibrated confidence string; absent it, the raw level is shown.
    """
    conf_map = confidence_map or {}
    cert = grade_certainty(card.ledger, card.verdict)
    rob = robustness(card.ledger)
    return {
        "id": id,
        "claim": card.claim,
        "verdict": card.verdict.value,
        "expected": expected,
        "certainty": cert.level,
        "certainty_signals": cert.signals,
        # Full per-domain GRADE profile: start tier + a signed delta per GRADE domain,
        # summing to the certainty score. Deterministic, auditable, no LLM.
        "certainty_start": {"score": cert.start, "label": cert.start_label},
        "certainty_domains": [
            {"name": d.name, "delta": d.delta, "rationale": d.rationale} for d in cert.domains
        ],
        # calibrated: the EMPIRICAL accuracy of this certainty level across the labeled set
        "confidence": conf_map.get(cert.level, cert.level),
        "robustness": {"stability": rob.stability, "survives_drop_largest": rob.survives_drop_largest,
                       "n_perturbations": rob.n_perturbations},
        # Verdict-over-time: the trajectory of this claim as its evidence accrued (deterministic).
        "timeline": [{"year": t.year, "verdict": t.verdict, "certainty": t.certainty,
                      "n": t.n_studies, "changed": t.changed} for t in verdict_over_time(card.ledger)],
        "baseline": baseline,
        "gate_trace": [{"gate": g.gate, "passed": g.passed, "detail": g.detail} for g in card.gate_trace],
        "ledger": [dataclasses.asdict(r) for r in card.ledger],
        # A deterministic "what would move this verdict" — an abstention becomes a research directive.
        "what_would_change_it": card.what_would_change_it,
        "disclaimer": card.disclaimer,
    }
