"""Repro — the verification layer for a manuscript's Methods + Key Resources.

Claude does EXTRACTION only (messy reagent prose -> typed resources). Deterministic gates
issue every verdict against public ground truth the model cannot fabricate:
  - cell lines   -> the ICLAC Register of Misidentified Cell Lines (bundled, offline)
  - antibodies   -> the Antibody Registry (catalog# -> RRID:AB_xxxxxxx)
  - rigor items  -> ARRIVE/MDAR/SABV presence checks
A missing datum -> INSUFFICIENT (abstain), never a guess. Every FAIL carries a citation.

The honest boundary: the cell-line and antibody gates are deterministic lookups (result = "rule").
Whether a knockout control was *run* is a labelled model judgment. We do not claim no LLM in the
loop; we claim the verdicts trace to a citable record, and the tool catches what a confident model
misses on the obscure long tail (see scripts/repro_iclac_benchmark.py: bare model 20% / tool 100%).
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

from .parse import call_tool

_ROOT = os.path.dirname(os.path.dirname(__file__))


# ---------------------------------------------------------------------------
# ICLAC misidentified-cell-line register — deterministic, bundled, offline.
# ---------------------------------------------------------------------------
_ICLAC: dict | None = None


def _load_iclac() -> dict:
    global _ICLAC
    if _ICLAC is None:
        with open(os.path.join(_ROOT, "benchmark/repro/iclac_register.json")) as f:
            _ICLAC = json.load(f)
    return _ICLAC


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


_ICLAC_SQUASH: dict | None = None


def _load_iclac_squash() -> dict:
    global _ICLAC_SQUASH
    if _ICLAC_SQUASH is None:
        _ICLAC_SQUASH = {}
        for key, rec in _load_iclac().items():
            _ICLAC_SQUASH.setdefault(_squash(key), rec)
    return _ICLAC_SQUASH


def _iclac_lookup(name: str) -> dict | None:
    """Robust match: extractors often return 'GR-M pancreatic carcinoma line' or 'SNB19'.
    Try the full name, then leading-token prefixes, in both normalized and hyphen/space-insensitive
    forms. The squashed form is only trusted at >=3 chars to avoid spurious 1-2 char collisions."""
    reg, sq = _load_iclac(), _load_iclac_squash()
    cand = re.sub(r"\(.*?\)", " ", name).strip()
    toks = [t for t in re.split(r"\s+", cand) if t]
    tries = [name, cand] + [" ".join(toks[:i]) for i in range(min(4, len(toks)), 0, -1)]
    for t in tries:
        if not t.strip():
            continue
        if _norm(t) in reg:
            return reg[_norm(t)]
        s = _squash(t)
        if len(s) >= 3 and s in sq:
            return sq[s]
    return None


@dataclass
class Finding:
    item: str            # e.g. "cell line: GR-M"
    kind: str            # "cell_line" | "antibody" | "rigor"
    result: str          # "FAIL" | "PASS" | "INSUFFICIENT"
    detail: str          # human-readable verdict
    evidence: str = ""   # verbatim phrase from the manuscript
    citation: str = ""   # e.g. "ICLAC-00010 · CVCL_0372"
    method: str = "rule"  # "rule" (deterministic lookup) | "model judgment"


def check_cell_line(name: str, evidence: str = "") -> Finding:
    """Deterministic: is this line on the ICLAC misidentified register? A FAIL is citable."""
    rec = _iclac_lookup(name)
    if rec:
        return Finding(
            item=f"cell line: {name}", kind="cell_line", result="FAIL",
            detail=(f"On the ICLAC Register of Misidentified Cell Lines — claimed "
                    f"{rec['claimed_origin'] or 'unspecified origin'}, actually **{rec['true_identity']}**. "
                    f"Authenticate by STR before use."),
            evidence=evidence, citation=f"ICLAC {rec['iclac_id']} · {rec['cvcl']}", method="rule")
    # Absence from the register is NOT proof of identity — stay honest.
    return Finding(
        item=f"cell line: {name}", kind="cell_line", result="PASS",
        detail=("Not on the ICLAC misidentified register. (Absence is not proof of identity — "
                "STR authentication still required.)"),
        evidence=evidence, citation="", method="rule")


# ---------------------------------------------------------------------------
# Antibody Registry — catalog# -> RRID. Live API with a bundled demo cache.
# ---------------------------------------------------------------------------
_AB_CACHE_PATH = os.path.join(_ROOT, "benchmark/repro/antibody_cache.json")


def _ab_cache() -> dict:
    if os.path.exists(_AB_CACHE_PATH):
        with open(_AB_CACHE_PATH) as f:
            return json.load(f)
    return {}


def check_antibody(name: str, vendor: str = "", catalog: str = "", evidence: str = "") -> Finding:
    """Resolve a catalog number to an RRID via the Antibody Registry (cache first, then live)."""
    q = (catalog or name).strip()
    label = name or f"{vendor} {catalog}".strip() or q
    hit = _ab_cache().get(_norm(q))
    if hit is None:
        try:
            url = "https://www.antibodyregistry.org/api/fts-antibodies?" + urllib.parse.urlencode(
                {"q": q, "page": 1, "size": 5})
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
                items = json.loads(resp.read()).get("items", [])
            if items:
                it = items[0]
                hit = {"rrid": f"RRID:AB_{it.get('accession')}",
                       "vendor": it.get("vendorName", ""), "catalog": it.get("catalogNum", "")}
        except Exception:  # noqa: BLE001
            hit = None
    if hit:
        return Finding(
            item=f"antibody: {label}", kind="antibody", result="PASS",
            detail=f"Resolves to {hit['rrid']} ({hit.get('vendor','')} {hit.get('catalog','')}).".strip(),
            evidence=evidence, citation=hit["rrid"], method="rule")
    return Finding(
        item=f"antibody: {label}", kind="antibody", result="INSUFFICIENT",
        detail="No RRID resolves for this reagent — add a validated catalog number and its RRID.",
        evidence=evidence, citation="", method="rule")


# ---------------------------------------------------------------------------
# Extraction (Claude, tool-use) — messy Methods prose -> typed resources.
# ---------------------------------------------------------------------------
_EXTRACT_TOOL = {
    "name": "emit_resources",
    "description": "Extract the key resources and rigor-reporting facts from a manuscript Methods section.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cell_lines": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string", "description": "the cell line designation ONLY, e.g. 'HeLa', "
                         "'SNB-19', 'GR-M' — exclude tissue/descriptor words like 'glioblastoma line'"},
                "evidence": {"type": "string", "description": "verbatim phrase"}}, "required": ["name"]}},
            "antibodies": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "vendor": {"type": "string"}, "catalog": {"type": "string"},
                "evidence": {"type": "string"}}, "required": ["name"]}},
            "rigor": {"type": "object", "properties": {
                "sex_reported": {"type": ["boolean", "null"]},
                "n_per_group_stated": {"type": ["boolean", "null"]},
                "randomization_stated": {"type": ["boolean", "null"]},
                "blinding_stated": {"type": ["boolean", "null"]},
                "evidence": {"type": "string"}}},
        },
        "required": ["cell_lines", "antibodies", "rigor"],
    },
}
_EXTRACT_SYSTEM = (
    "You extract ONLY what is explicitly written in a manuscript Methods/Key-Resources section into a "
    "structured resource inventory. Put the verbatim phrase in each 'evidence' field. For rigor flags, "
    "set true only if the fact is explicitly stated, false if the section clearly omits it, null if "
    "there is no basis to judge. Never infer identities or catalog numbers.")


def extract_resources(methods_text: str) -> dict:
    return call_tool(_EXTRACT_SYSTEM, f"Methods:\n\n{methods_text}", _EXTRACT_TOOL, max_tokens=2048)


# ---------------------------------------------------------------------------
# Rigor-reporting gates (ARRIVE/MDAR/SABV presence checks).
# ---------------------------------------------------------------------------
_RIGOR_ITEMS = [
    ("sex_reported", "Sex of animals/cells reported (SABV)", "NOT-OD-15-102"),
    ("n_per_group_stated", "Sample size (n) per group stated", "ARRIVE 2.0 #2"),
    ("randomization_stated", "Randomization stated", "ARRIVE 2.0 #4"),
    ("blinding_stated", "Blinding stated", "ARRIVE 2.0 #5"),
]


def rigor_findings(rigor: dict) -> list[Finding]:
    ev = rigor.get("evidence", "")
    out = []
    for key, label, cite in _RIGOR_ITEMS:
        v = rigor.get(key)
        if v is True:
            out.append(Finding(label, "rigor", "PASS", "Reported.", ev, cite, "model judgment"))
        elif v is False:
            out.append(Finding(label, "rigor", "FAIL", "Required element not reported.", ev, cite, "model judgment"))
        else:
            out.append(Finding(label, "rigor", "INSUFFICIENT", "Could not determine from the text.", ev, cite, "model judgment"))
    return out


# ---------------------------------------------------------------------------
# Roll-up.
# ---------------------------------------------------------------------------
@dataclass
class ReproReport:
    findings: list[Finding]
    verdict: str          # "Submission-ready" | "Needs fixes" | "Needs verification"
    n_fail: int
    n_pass: int
    n_insufficient: int
    to_fix: list[str] = field(default_factory=list)


def aggregate(findings: list[Finding]) -> str:
    if any(f.result == "FAIL" for f in findings):
        return "Needs fixes"
    if any(f.result == "INSUFFICIENT" for f in findings):
        return "Needs verification"
    return "Submission-ready"


def review(methods_text: str) -> ReproReport:
    """End-to-end: Methods text -> extracted resources -> deterministic gates -> report."""
    res = extract_resources(methods_text)
    findings: list[Finding] = []
    for cl in res.get("cell_lines", []):
        findings.append(check_cell_line(cl.get("name", ""), cl.get("evidence", "")))
    for ab in res.get("antibodies", []):
        findings.append(check_antibody(ab.get("name", ""), ab.get("vendor", ""),
                                       ab.get("catalog", ""), ab.get("evidence", "")))
    findings += rigor_findings(res.get("rigor", {}))
    verdict = aggregate(findings)
    to_fix = [f"{f.item} — {f.detail}" for f in findings if f.result in ("FAIL", "INSUFFICIENT")]
    return ReproReport(
        findings=findings, verdict=verdict,
        n_fail=sum(1 for f in findings if f.result == "FAIL"),
        n_pass=sum(1 for f in findings if f.result == "PASS"),
        n_insufficient=sum(1 for f in findings if f.result == "INSUFFICIENT"),
        to_fix=to_fix)


def report_to_dict(r: ReproReport) -> dict:
    d = asdict(r)
    return d


# ---------------------------------------------------------------------------
# The bare-LLM foil — what a confident model says about the same resources.
# Used only for the demo contrast; never part of a verdict.
# ---------------------------------------------------------------------------
_FOIL_TOOL = {
    "name": "assess",
    "description": "Assess the reagents in a Methods section from your own knowledge.",
    "input_schema": {"type": "object", "properties": {
        "answer": {"type": "string", "description": "one or two sentences: are the cell lines and antibodies fine to use?"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]}}, "required": ["answer", "confidence"]},
}


def bare_llm_foil(methods_text: str) -> dict:
    return call_tool(
        "You are a helpful lab assistant. Answer from your own knowledge; do not hedge.",
        f"In this Methods section, are the cell lines and antibodies fine to use, or are any "
        f"misidentified / unvalidated?\n\n{methods_text}", _FOIL_TOOL, max_tokens=300)
