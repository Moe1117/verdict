"""The frozen-corpora -> verdict path is fully testable offline (no LLM, no net)."""
import os

from verdict.corpora import load_path
from verdict.gates import Verdict, resolve
from verdict.verdict import evaluate

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_corpus.json")


def test_frozen_corpus_loads_and_resolves():
    meta, rows = load_path(FIXTURE)
    assert len(rows) == 3
    card = evaluate(meta["claim"], rows)
    # The lone retracted "positive" RCT is integrity-screened out; the clean
    # high-tier evidence is null -> Not Supported.
    assert card.verdict is Verdict.NOT_SUPPORTED
    assert card.verdict.value == meta["expected_verdict"]


def test_integrity_row_is_excluded_from_the_decision():
    _, rows = load_path(FIXTURE)
    excluded = [r for r in rows if not r.integrity_ok]
    assert len(excluded) == 1 and excluded[0].direction == 1
    # Without the screen a naive engine would see a positive RCT; with it -> Not Supported.
    assert resolve(rows)[0] is Verdict.NOT_SUPPORTED
