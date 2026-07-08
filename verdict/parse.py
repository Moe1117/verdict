"""Claim -> structured tuple. The one place ambiguity is made explicit.

Uses Claude for structured output. Also the input guard: if the claim is
ill-posed or its outcome is not objectively measurable, return UNDECIDABLE here
rather than pretending to grade it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClaimTuple:
    raw: str
    agent: str
    outcome: str
    population: str
    direction: int          # +1 "increases/improves", -1 "reduces", per the claim
    measurable: bool = True  # False -> UNDECIDABLE (input guard)
    proxies: list[str] | None = None


def parse_claim(raw: str) -> ClaimTuple:
    """TODO: Claude structured-output call. Normalize the claim; flag ill-posed
    / unmeasurable claims as measurable=False so the engine returns UNDECIDABLE."""
    raise NotImplementedError
