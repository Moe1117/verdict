"""Claim -> structured tuple. The one place ambiguity is made explicit.

Uses Claude for structured output (forced tool-use). Also the input guard: if the
claim is ill-posed or its outcome is not objectively measurable, flag it here
(measurable=False) so the engine abstains rather than pretending to grade it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODEL = "claude-sonnet-5"


def model() -> str:
    """Resolve the extraction/parse model at call time. An empty VERDICT_MODEL (as in a
    freshly-copied .env) is treated as unset, not as a blank model id."""
    return os.getenv("VERDICT_MODEL") or DEFAULT_MODEL


@dataclass
class ClaimTuple:
    raw: str
    agent: str
    outcome: str
    population: str
    direction: int          # +1 "increases/improves", -1 "reduces", per the claim
    measurable: bool = True  # False -> ill-posed / not objectively measurable (input guard)
    proxies: list[str] | None = None


_TOOL = {
    "name": "claim",
    "description": "The structured decomposition of a biomedical efficacy claim.",
    "input_schema": {
        "type": "object",
        "properties": {
            "agent": {"type": "string", "description": "the intervention / drug"},
            "outcome": {"type": "string", "description": "the specific clinical outcome claimed"},
            "population": {"type": "string", "description": "the patient population"},
            "direction": {"type": "integer", "enum": [-1, 1],
                          "description": "+1 if the claim asserts improvement/increase, -1 if reduction"},
            "measurable": {"type": "boolean",
                           "description": "false if the claim is ill-posed, vague, or its outcome is not "
                                          "objectively measurable in humans (input guard)"},
            "proxies": {"type": "array", "items": {"type": "string"},
                        "description": "accepted surrogate endpoints for this outcome, if any"},
            "search_query": {"type": "string", "description": "a focused PubMed/ClinicalTrials.gov query"},
        },
        "required": ["agent", "outcome", "population", "direction", "measurable", "search_query"],
    },
}

_SYSTEM = (
    "You decompose a biomedical efficacy claim into structured parts for an evidence engine. "
    "Be literal about the CLAIMED outcome (e.g. 'reduces mortality' -> outcome is mortality, not a "
    "surrogate). Set measurable=false only for genuinely ill-posed or unmeasurable claims."
)


def call_tool(system: str, user: str, tool: dict, max_tokens: int = 1024) -> dict:
    """Force a single structured tool call and return its input dict. Lazily imports the
    anthropic SDK so retrieval and the deterministic engine work without it / without a key."""
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model(), max_tokens=max_tokens, system=system, tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user}],
    )
    for block in msg.content:
        if block.type == "tool_use":
            return dict(block.input)
    raise RuntimeError("model returned no structured tool call")


def parse_claim(raw: str) -> tuple[ClaimTuple, str]:
    """Return (ClaimTuple, search_query). Requires ANTHROPIC_API_KEY."""
    d = call_tool(_SYSTEM, f"Claim: {raw}", _TOOL)
    ct = ClaimTuple(
        raw=raw, agent=d["agent"], outcome=d["outcome"], population=d["population"],
        direction=int(d["direction"]), measurable=bool(d.get("measurable", True)),
        proxies=d.get("proxies") or [],
    )
    return ct, d.get("search_query", f"{d['agent']} {d['outcome']} {d['population']}")
