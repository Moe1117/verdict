"""Agentic Investigator — Claude autonomously searches real public APIs (PubMed, Cellosaurus, the
Antibody Registry) for real-citation evidence of an antibody's knockout validation or a cell line's
misidentification provenance. A deterministic gate guarantees no fabricated citation survives: Claude
navigates the literature, but only ids the tools actually returned may be cited.

This is the one place Claude is a multi-step AGENT (search -> read -> decide), labelled a 'model
investigation'. It never issues a deterministic identity verdict and never flips the /api/repro headline.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

_NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_CELLO = "https://api.cellosaurus.org"


def _http_get(url: str, timeout: int = 12) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")

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


class Retriever:
    """Real retrieval over public APIs. Every id it returns is logged in `retrieved` — the ground truth
    the citation-verification gate checks against. All methods degrade to empty on any error."""

    def __init__(self, email: str = ""):
        self.email = email or os.getenv("NCBI_EMAIL", "")
        self.retrieved: set = set()
        self.n_search = 0
        self.n_fetch = 0

    def _eutil(self, tool: str, params: dict) -> str:
        params = {**params, "tool": "verdict", "email": self.email}
        return _http_get(f"{_NCBI}/{tool}?{urllib.parse.urlencode(params)}")

    def pubmed_search(self, query: str, retmax: int = 6) -> list:
        self.n_search += 1
        try:
            d = json.loads(self._eutil("esearch.fcgi", {
                "db": "pubmed", "term": query, "retmax": retmax, "retmode": "json"}))
            ids = list(d.get("esearchresult", {}).get("idlist", []))
        except Exception:  # noqa: BLE001
            return []
        for pid in ids:
            self.retrieved.add(f"PMID:{pid}")
        return ids

    def pubmed_fetch(self, pmids: list) -> dict:
        self.n_fetch += 1
        pmids = [str(p) for p in pmids][:6]
        if not pmids:
            return {}
        try:
            text = self._eutil("efetch.fcgi", {
                "db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "text"})
        except Exception:  # noqa: BLE001
            return {}
        for pid in pmids:
            self.retrieved.add(f"PMID:{pid}")
        # one text blob per batch; a single-pmid fetch is keyed by that pmid (Claude reads the blob)
        return {pmids[0]: text} if len(pmids) == 1 else {"_pmids": pmids, "_text": text}

    def cellosaurus_lookup(self, name_or_cvcl: str) -> dict:
        try:
            body = _http_get(f"{_CELLO}/cell-line/{urllib.parse.quote(name_or_cvcl)}?format=json")
            cl = json.loads(body)["Cellosaurus"]["cell-line-list"][0]
        except Exception:  # noqa: BLE001
            return {}
        cvcl = next((a["value"] for a in cl.get("accession-list", []) if a.get("type") == "primary"), "")
        problem = " ".join(c.get("value", "") for c in cl.get("comment-list", [])
                           if "roblematic" in c.get("category", ""))
        pmids = re.findall(r"PubMed=(\d+)", json.dumps(cl))
        if cvcl:
            self.retrieved.add(cvcl)
        for pid in pmids:
            self.retrieved.add(f"PMID:{pid}")
        return {"cvcl": cvcl, "problem": problem, "reference_pmids": pmids}
