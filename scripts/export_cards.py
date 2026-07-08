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

# The demo deck: an explicit, story-ordered subset of the benchmark corpora.
# The first four tabs show all four verdict states; the hero cases (fraud-immunity
# C08, abstention C09) lead. F02/F03 stay in the benchmark for the honest eval but
# are excluded here: the gate engine over-decides them (Contested vs Insufficient,
# Not Supported vs Contested), and a card badged "never confidently wrong" must not
# show a wrong verdict on stage.
DEMO_DECK = ["C08", "C09", "C01", "C14", "F04", "F01", "C05"]


def main() -> None:
    os.makedirs(WEB_PUBLIC, exist_ok=True)
    have = set(available())
    cards = []
    for cid in DEMO_DECK:
        if cid not in have:
            print(f"  ! skipping {cid}: no corpus file")
            continue
        meta, rows = load_rows(cid)
        card = evaluate(meta["claim"], rows)
        cards.append({
            "id": cid,
            "claim": card.claim,
            "verdict": card.verdict.value,
            "expected": meta.get("expected_verdict"),
            "confidence": "high",  # curated deck: all seven are high-confidence gold cases
            "gate_trace": [{"gate": g.gate, "passed": g.passed, "detail": g.detail} for g in card.gate_trace],
            "ledger": [dataclasses.asdict(r) for r in card.ledger],
            "disclaimer": card.disclaimer,
        })
    with open(os.path.join(WEB_PUBLIC, "cards.json"), "w") as fh:
        json.dump(cards, fh, indent=2)
    print(f"wrote {len(cards)} cards -> web/public/cards.json")
    for c in cards:
        print(f"  {c['id']}: {c['verdict']}")


if __name__ == "__main__":
    main()
