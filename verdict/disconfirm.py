"""Falsification query: given a DECIDED verdict, build a PubMed query that hunts for the evidence
that would CONTRADICT it. Deterministic (no LLM) — the live path uses this to actively seek
disconfirming trials before it commits, so a verdict that survives has survived an attempt to
refute it, and a missed contradicting trial gets a real chance to surface and flip the gate.

Only decided verdicts get a query. An abstention (Contested / Insufficient / Undecidable) is
already withholding — there is nothing to try to overturn.
"""
from __future__ import annotations

from .gates import Verdict
from .parse import ClaimTuple

# Terms that bias PubMed relevance toward the OPPOSITE finding.
_NULL_TERMS = '"no effect" OR "did not" OR failed OR "no benefit" OR nonsignificant OR negative'
_EFFECT_TERMS = 'improved OR reduced OR benefit OR efficacy OR "significant reduction"'


def disconfirming_query(ct: ClaimTuple, verdict: Verdict) -> str | None:
    """A query aimed at the evidence that would overturn `verdict` for this claim, or None."""
    core = f"{ct.agent} {ct.outcome}".strip()
    if verdict is Verdict.SUPPORTED:
        # We concluded the effect is present -> look hard for null / negative / failed trials.
        return f"{core} ({_NULL_TERMS})"
    if verdict is Verdict.NOT_SUPPORTED:
        # We concluded no effect -> look hard for trials that DID show a benefit.
        return f"{core} ({_EFFECT_TERMS})"
    return None
