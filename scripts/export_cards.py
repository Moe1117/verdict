"""Resolve every frozen corpus into a VerdictCard JSON for the web UI.

Output: web/public/cards.json (array). Deterministic; no network, no LLM — the
UI replays these pre-resolved cards so the demo can never fail live.
"""
from __future__ import annotations

import dataclasses
import json
import os

from verdict.corpora import available, load_rows
from verdict.verdict import evaluate

WEB_PUBLIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "public")
_ORDER = {"Supported": 0, "Not Supported": 1, "Contested": 2, "Insufficient": 3}


def main() -> None:
    os.makedirs(WEB_PUBLIC, exist_ok=True)
    cards = []
    for cid in available():
        meta, rows = load_rows(cid)
        card = evaluate(meta["claim"], rows)
        cards.append({
            "id": cid,
            "claim": card.claim,
            "verdict": card.verdict.value,
            "expected": meta.get("expected_verdict"),
            "confidence": "high",  # all five are high-confidence gold cases
            "gate_trace": [{"gate": g.gate, "passed": g.passed, "detail": g.detail} for g in card.gate_trace],
            "ledger": [dataclasses.asdict(r) for r in card.ledger],
            "disclaimer": card.disclaimer,
        })
    cards.sort(key=lambda c: _ORDER.get(c["verdict"], 9))
    with open(os.path.join(WEB_PUBLIC, "cards.json"), "w") as fh:
        json.dump(cards, fh, indent=2)
    print(f"wrote {len(cards)} cards -> web/public/cards.json")
    for c in cards:
        print(f"  {c['id']}: {c['verdict']}")


if __name__ == "__main__":
    main()
