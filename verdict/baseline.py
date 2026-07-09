"""The plain-LLM foil: a real Claude call that answers a claim DIRECTLY — no tools, no evidence,
no gates — the way a chat model does when asked offhand. This is the honest control the whole
project is measured against: the SAME Claude, naive, vs Claude wrapped in the decidable-gates
architecture. Used both live in the web "Duel" and to (re)generate the benchmark's baselines, so the
scorecard comparison is a real, reproducible model call — never a cached string.
"""
from __future__ import annotations

import logging

log = logging.getLogger("verdict.baseline")

_FOIL_TOOL = {
    "name": "answer",
    "description": "A direct, confident yes/no answer to a clinical efficacy claim, as a general "
                   "assistant would give it without consulting sources.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "enum": ["Yes", "No"]},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "text": {"type": "string", "description": "one confident sentence, no hedging, no citations"},
        },
        "required": ["answer", "confidence", "text"],
    },
}
_FOIL_SYSTEM = ("You are a general-purpose assistant answering a clinical question directly and "
                "confidently, the way a chat model does when asked offhand — no tools, no sources, "
                "no hedging. Give a single decisive sentence.")


def plain_llm_baseline(claim: str) -> dict | None:
    """One confident, unsourced Claude answer to `claim`. Non-fatal: returns None on any error so a
    failed foil never breaks resolution (callers fall back to a generic answer)."""
    try:
        from .parse import call_tool
        d = call_tool(_FOIL_SYSTEM, f"Claim: {claim}", _FOIL_TOOL, max_tokens=300)
        return {"answer": d.get("answer", "Yes"), "confidence": d.get("confidence", "high"),
                "text": d.get("text", "")}
    except Exception:  # noqa: BLE001 — the foil is a control; never let it sink the caller
        log.warning("plain_llm_baseline failed", exc_info=True)
        return None
