"""The frozen deck and the live API must serialize a VerdictCard identically — one shared
serializer, so the two paths can never drift. This pins card_payload() to reproduce, key-for-key,
the committed frozen cards.json that scripts/export_cards.py produced, and to degrade cleanly for a
live claim that carries no corpus metadata (no expected verdict, no canned baseline)."""
import json
import os

import pytest

from verdict.cards import card_payload
from verdict.corpora import load_rows
from verdict.gates import EvidenceRow
from verdict.verdict import evaluate

ROOT = os.path.dirname(os.path.dirname(__file__))
CARDS = json.load(open(os.path.join(ROOT, "web", "public", "cards.json")))
CALIB = json.load(open(os.path.join(ROOT, "web", "public", "calibration.json")))
CONF_MAP = {b["level"]: b["confidence"] for b in CALIB.get("buckets", [])}


@pytest.mark.parametrize("frozen", CARDS, ids=[c["id"] for c in CARDS])
def test_card_payload_reproduces_frozen_deck(frozen):
    """card_payload must reproduce every frozen card exactly — else frozen and live have drifted."""
    cid = frozen["id"]
    meta, rows = load_rows(cid)
    card = evaluate(meta["claim"], rows)
    got = card_payload(card, id=cid, expected=meta.get("expected_verdict"),
                       baseline=meta.get("baseline"), confidence_map=CONF_MAP)
    assert got == frozen


def test_card_payload_undecidable_emits_no_fabricated_grade_profile():
    """An ill-posed claim is rejected at the input guard (Undecidable) — there is no evidence body,
    so the card must NOT show a fabricated per-domain GRADE certainty analysis."""
    from verdict.gates import GateTrace, Verdict
    from verdict.verdict import VerdictCard
    card = VerdictCard(claim="does this vibe well", verdict=Verdict.UNDECIDABLE, confidence=None,
                       ledger=[], gate_trace=[GateTrace("input-guard", False, "not measurable")])
    got = card_payload(card, id="LIVE")
    assert got["verdict"] == "Undecidable"
    assert got["certainty_domains"] == []   # no GRADE analysis of evidence that was never gathered


def test_card_payload_live_shape_without_meta():
    """A live claim carries no meta: expected/baseline are null, but every key the web Card
    interface consumes is still present and the verdict/certainty are computed from the rows."""
    rows = [EvidenceRow(citation="c", design="rct", direction=1, population_match=True,
                        source_id="PMID:1", n_int=5000, year=2020)]
    card = evaluate("drugX reduces mortality in adults", rows)
    got = card_payload(card, id="LIVE")
    assert got["id"] == "LIVE"
    assert got["expected"] is None
    assert got["baseline"] is None
    assert got["verdict"] == card.verdict.value
    for key in ("claim", "verdict", "certainty", "certainty_signals", "certainty_start",
                "certainty_domains", "confidence", "robustness", "timeline",
                "gate_trace", "ledger", "disclaimer"):
        assert key in got, f"missing key {key!r}"
