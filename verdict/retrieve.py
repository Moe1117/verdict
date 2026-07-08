"""Evidence retrieval from PUBLIC sources only: PubMed (NCBI E-utilities) and
ClinicalTrials.gov v2. No paid APIs, no scraping. Every E-utilities call sends
tool= and email= per NCBI policy.

Only citation metadata is retained/displayed. Abstract text is fetched
transiently for extraction and never stored verbatim in the repo.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CTGOV = "https://clinicaltrials.gov/api/v2"


@dataclass
class Source:
    kind: str        # "pubmed" | "clinicaltrials"
    id: str          # "PMID:..." | "NCT:..."
    title: str
    authors: str
    journal: str
    year: str
    url: str
    # Deterministic integrity signal read from the source database's own metadata (e.g. PubMed
    # publication type). "" = not flagged; "retracted" / "expression_of_concern" otherwise.
    integrity_severity: str = ""


# PubMed publication types that mark a compromised record, mapped to our severity vocabulary.
# These are catalogued by NLM on the article itself — a deterministic, citable fact, not a guess.
RETRACTION_PUBTYPES = {
    "Retracted Publication": "retracted",
    "Expression of Concern": "expression_of_concern",
}


def retraction_severity(pubtypes: list[str] | None) -> str:
    """Highest-severity integrity flag among a PubMed record's publication types, or ""."""
    for pt in pubtypes or []:
        sev = RETRACTION_PUBTYPES.get(pt)
        if sev == "retracted":
            return sev  # retraction outranks an expression of concern
    for pt in pubtypes or []:
        if RETRACTION_PUBTYPES.get(pt) == "expression_of_concern":
            return "expression_of_concern"
    return ""


def retraction_note(source: Source) -> str:
    """Citable integrity note for a database-flagged source (empty if not flagged)."""
    label = {"retracted": "RETRACTED", "expression_of_concern": "EXPRESSION OF CONCERN"}.get(
        source.integrity_severity, "")
    if not label:
        return ""
    return f"{label} — flagged by PubMed publication type (deterministic, not LLM-judged): {source.url}"


def _ncbi_params() -> dict:
    p = {"tool": os.getenv("NCBI_TOOL", "verdict"), "email": os.getenv("NCBI_EMAIL", "")}
    if os.getenv("NCBI_API_KEY"):
        p["api_key"] = os.environ["NCBI_API_KEY"]
    return p


def _pause() -> None:
    # NCBI: <=3 req/s without an API key. Be polite.
    time.sleep(0.12 if os.getenv("NCBI_API_KEY") else 0.34)


def search_pubmed(query: str, retmax: int = 20, timeout: float = 20.0) -> list[Source]:
    r = httpx.get(f"{EUTILS}/esearch.fcgi", params={
        **_ncbi_params(), "db": "pubmed", "term": query,
        "retmax": retmax, "retmode": "json", "sort": "relevance",
    }, timeout=timeout)
    r.raise_for_status()
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    _pause()
    s = httpx.get(f"{EUTILS}/esummary.fcgi", params={
        **_ncbi_params(), "db": "pubmed", "id": ",".join(ids), "retmode": "json",
    }, timeout=timeout)
    s.raise_for_status()
    res = s.json().get("result", {})
    out: list[Source] = []
    for pid in res.get("uids", []):
        d = res.get(pid, {})
        authors = ", ".join(a.get("name", "") for a in d.get("authors", [])[:3])
        out.append(Source(
            kind="pubmed", id=f"PMID:{pid}", title=d.get("title", ""),
            authors=authors, journal=d.get("fulljournalname") or d.get("source", ""),
            year=(d.get("pubdate", "") or "")[:4],
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
            # Deterministic retraction / expression-of-concern flag from NLM's own publication
            # type — populated here in the SAME esummary call, so it costs no extra request.
            integrity_severity=retraction_severity(d.get("pubtype")),
        ))
    return out


def fetch_abstract(pmid: str, timeout: float = 20.0) -> str:
    """Fetch abstract text transiently for extraction. Not stored verbatim."""
    pid = pmid.replace("PMID:", "")
    r = httpx.get(f"{EUTILS}/efetch.fcgi", params={
        **_ncbi_params(), "db": "pubmed", "id": pid, "rettype": "abstract", "retmode": "text",
    }, timeout=timeout)
    r.raise_for_status()
    return r.text


def search_trials(query: str, page_size: int = 20, timeout: float = 20.0) -> list[Source]:
    r = httpx.get(f"{CTGOV}/studies", params={
        "query.term": query, "pageSize": page_size, "format": "json",
    }, timeout=timeout)
    r.raise_for_status()
    out: list[Source] = []
    for st in r.json().get("studies", []):
        idm = st.get("protocolSection", {}).get("identificationModule", {})
        nct = idm.get("nctId", "")
        if not nct:
            continue
        out.append(Source(
            kind="clinicaltrials", id=f"NCT:{nct}", title=idm.get("briefTitle", ""),
            authors="", journal="ClinicalTrials.gov", year="",
            url=f"https://clinicaltrials.gov/study/{nct}",
        ))
    return out
