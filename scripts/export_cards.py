"""Resolve every frozen corpus into a VerdictCard JSON for the web UI.

Output: web/public/cards.json (array). Deterministic; no network, no LLM — the
UI replays these pre-resolved cards so the demo can never fail live.
"""
from __future__ import annotations

import json
import os

from verdict.cards import card_payload
from verdict.corpora import available, load_rows
from verdict.verdict import evaluate

WEB_PUBLIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "public")


def _calibrated_confidence() -> dict:
    """certainty level -> calibrated confidence string, from calibration.json if present."""
    path = os.path.join(WEB_PUBLIC, "calibration.json")
    if not os.path.exists(path):
        return {}
    data = json.load(open(path))
    return {b["level"]: b["confidence"] for b in data.get("buckets", [])}

# The demo deck: an explicit, story-ordered subset of the clinical benchmark.
# The first four tabs span all four verdict states; the Alzheimer's trio (aducanumab
# Contested, lecanemab Supported, solanezumab Not Supported) shows three honest verdicts
# on one drug class. Real breakthrough medicines + the fraud-immunity beat (ivermectin).
DEMO_DECK = ["M06", "M07", "M09", "M24", "M01", "M12", "M11", "M23", "C08"]


def main() -> None:
    os.makedirs(WEB_PUBLIC, exist_ok=True)
    have = set(available())
    conf_map = _calibrated_confidence()
    cards = []
    for cid in DEMO_DECK:
        if cid not in have:
            print(f"  ! skipping {cid}: no corpus file")
            continue
        meta, rows = load_rows(cid)
        card = evaluate(meta["claim"], rows)
        # One shared serializer for the frozen deck and the live API — they can never drift.
        cards.append(card_payload(
            card, id=cid, expected=meta.get("expected_verdict"),
            baseline=meta.get("baseline"),  # per-corpus plain-LLM answer (clinical corpora carry their own)
            confidence_map=conf_map,
        ))
    with open(os.path.join(WEB_PUBLIC, "cards.json"), "w") as fh:
        json.dump(cards, fh, indent=2)
    print(f"wrote {len(cards)} cards -> web/public/cards.json")
    for c in cards:
        print(f"  {c['id']}: {c['verdict']}")


if __name__ == "__main__":
    main()
