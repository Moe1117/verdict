"""Turn a verdict into a research directive: the specific evidence that would move it.

Deterministic (no LLM), read straight from the gate outcome. For an abstention (Insufficient /
Contested) this is the most useful thing the system can say — not just "we can't decide", but
*exactly what evidence would let anyone decide*. For a decided verdict it states the falsifier:
the result that would overturn it. Same rows in -> same directive out.
"""
from __future__ import annotations

from .gates import GateTrace, Verdict


def research_directive(verdict: Verdict, gate_trace: list[GateTrace]) -> str:
    gates = {g.gate: g for g in gate_trace}

    if verdict is Verdict.UNDECIDABLE:
        return "Restate the claim as a specific, objectively measurable clinical outcome in a defined population."

    if verdict is Verdict.INSUFFICIENT:
        de = gates.get("direct-evidence")
        if de is not None and not de.passed and "surrogate" in de.detail.lower():
            return ("A randomized trial measuring the claimed clinical outcome directly — not a "
                    "surrogate endpoint — would make this decidable.")
        if de is not None and not de.passed:
            return ("An on-population randomized controlled trial, or a meta-analysis of RCTs, "
                    "measuring the claimed outcome would make this decidable.")
        # direct evidence exists but was too thin (sufficiency gate failed)
        return ("A second concordant RCT, a single large trial (n≥300), or a meta-analysis of "
                "RCTs would lift the evidence above the sufficiency threshold.")

    if verdict is Verdict.CONTESTED:
        return ("A definitive large RCT (n≥1000), or a current meta-analysis of RCTs, agreeing "
                "with one side would resolve the conflict.")

    if verdict is Verdict.SUPPORTED:
        return "A large RCT or meta-analysis of RCTs showing no effect on-population would overturn this verdict."

    if verdict is Verdict.NOT_SUPPORTED:
        return "A large RCT or meta-analysis of RCTs showing a benefit on-population would overturn this verdict."

    return ""
