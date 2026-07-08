"""Evidence retrieval from PUBLIC sources only: PubMed (NCBI E-utilities) and
ClinicalTrials.gov. No paid APIs, no scraping. Every E-utilities call must send
tool= and email= per NCBI policy.

For reproducibility during the hackathon, retrieved corpora are frozen per claim
under benchmark/corpora/ so verdicts reproduce without live network calls.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CTGOV = "https://clinicaltrials.gov/api/v2"


@dataclass
class Source:
    kind: str        # "pubmed" | "clinicaltrials"
    id: str          # PMID or NCT id
    title: str
    year: str
    url: str


def _ncbi_params() -> dict:
    return {"tool": os.getenv("NCBI_TOOL", "verdict"), "email": os.getenv("NCBI_EMAIL", "")}


def search_pubmed(query: str, retmax: int = 25) -> list[Source]:
    """TODO: esearch -> esummary via E-utilities (metadata only; no full text)."""
    raise NotImplementedError


def search_trials(query: str, page_size: int = 25) -> list[Source]:
    """TODO: ClinicalTrials.gov v2 study search (public domain)."""
    raise NotImplementedError
