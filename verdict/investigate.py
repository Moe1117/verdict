"""Agentic Investigator — Claude autonomously searches real public APIs (PubMed, Cellosaurus, the
Antibody Registry) for real-citation evidence of an antibody's knockout validation or a cell line's
misidentification provenance. A deterministic gate guarantees no fabricated citation survives: Claude
navigates the literature, but only ids the tools actually returned may be cited.

This is the one place Claude is a multi-step AGENT (search -> read -> decide), labelled a 'model
investigation'. It never issues a deterministic identity verdict and never flips the /api/repro headline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Terminal verdicts.
_ANTIBODY_FOUND = "FOUND_VALIDATION"     # a real PMID shows a genetic validation of this antibody
_ANTIBODY_NONE = "NO_VALIDATION_FOUND"   # searched, found none — honest abstention
_CELL_FULL = "PROVENANCE_CHAIN"          # CVCL + a real primary-reference PMID
_CELL_PARTIAL = "PARTIAL"                # only part of the chain could be grounded
_INCONCLUSIVE = "INCONCLUSIVE"           # tool/loop failure — graceful degradation


@dataclass
class Citation:
    id: str            # "PMID:12345" | "CVCL_2451" | "RRID:AB_..."
    kind: str          # "pubmed" | "cellosaurus" | "antibody_registry"
    title: str = ""
    why: str = ""      # one line: why this supports the verdict


@dataclass
class Investigation:
    kind: str          # "antibody" | "cell_line"
    verdict: str
    cited: list = field(default_factory=list)
    reasoning: str = ""
    steps: list = field(default_factory=list)   # human-readable agentic trail (for the UI)
    grounded: bool = False
    method: str = "model investigation"


def verify_citations(inv: Investigation, retrieved: set) -> Investigation:
    """Deterministic grounding gate: keep only citations whose id was actually retrieved by a tool;
    downgrade an ungrounded 'found' verdict to abstain. Fabricated citations cannot survive this."""
    kept = [c for c in inv.cited if c.id in retrieved]
    inv.cited = kept
    inv.grounded = bool(kept)
    has_pubmed = any(c.kind == "pubmed" for c in kept)
    if inv.kind == "antibody" and inv.verdict == _ANTIBODY_FOUND and not has_pubmed:
        inv.verdict = _ANTIBODY_NONE
    if inv.kind == "cell_line" and inv.verdict == _CELL_FULL and not has_pubmed:
        inv.verdict = _CELL_PARTIAL  # the CVCL may still be grounded, but the primary reference is not
    return inv
