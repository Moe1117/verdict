"""The falsification query: given a DECIDED verdict, build a PubMed query that hunts for the
evidence that would contradict it. Deterministic (no LLM). Only decided verdicts get one —
abstentions (Contested / Insufficient / Undecidable) are already withholding, nothing to refute."""
from verdict.disconfirm import disconfirming_query
from verdict.gates import Verdict
from verdict.parse import ClaimTuple


def _ct(agent="drugX", outcome="mortality", direction=-1):
    return ClaimTuple(raw="x", agent=agent, outcome=outcome, population="adults", direction=direction)


def test_supported_seeks_null_or_negative_evidence():
    q = disconfirming_query(_ct(), Verdict.SUPPORTED)
    assert "drugX" in q and "mortality" in q
    assert any(w in q.lower() for w in ("no effect", "did not", "failed", "no benefit", "nonsignificant"))


def test_not_supported_seeks_positive_evidence():
    q = disconfirming_query(_ct(), Verdict.NOT_SUPPORTED)
    assert "drugX" in q
    assert any(w in q.lower() for w in ("improved", "reduced", "benefit", "efficacy"))


def test_abstentions_and_undecidable_have_no_disconfirming_query():
    assert disconfirming_query(_ct(), Verdict.CONTESTED) is None
    assert disconfirming_query(_ct(), Verdict.INSUFFICIENT) is None
    assert disconfirming_query(_ct(), Verdict.UNDECIDABLE) is None
