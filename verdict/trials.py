"""Thin ClinicalTrials.gov REST v2 client. Retrieval only; no matching logic."""
from __future__ import annotations
import json, urllib.parse, urllib.request
from dataclasses import dataclass

API = "https://clinicaltrials.gov/api/v2/studies"

@dataclass
class Candidate:
    nct_id: str
    title: str
    status: str

@dataclass
class Eligibility:
    nct_id: str
    text: str
    minimum_age: str
    maximum_age: str
    sex: str

def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def search_candidates_by_condition(condition: str, page_size: int = 5,
                                   status: str = "RECRUITING") -> list[Candidate]:
    q = urllib.parse.urlencode({
        "query.cond": condition, "filter.overallStatus": status,
        "pageSize": page_size, "fields": "NCTId,BriefTitle,OverallStatus"})
    data = _get_json(f"{API}?{q}")
    out: list[Candidate] = []
    for s in data.get("studies", []):
        idm = s.get("protocolSection", {}).get("identificationModule", {})
        stm = s.get("protocolSection", {}).get("statusModule", {})
        nct = idm.get("nctId", "")
        if nct:
            out.append(Candidate(nct, idm.get("briefTitle", ""), stm.get("overallStatus", "")))
    return out

def get_eligibility(nct_id: str) -> Eligibility:
    data = _get_json(f"{API}/{nct_id}")
    em = data.get("protocolSection", {}).get("eligibilityModule", {})
    return Eligibility(nct_id, em.get("eligibilityCriteria", ""),
                       em.get("minimumAge", ""), em.get("maximumAge", ""), em.get("sex", ""))
