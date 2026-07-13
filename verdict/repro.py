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
misses on the obscure long tail (see scripts/repro_iclac_benchmark.py: a frontier model correctly
identifies ~18% of known-contaminated lines; the tool catches ~92% end-to-end, every FAIL cited).
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

from .knockout import assess_knockout_control
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


# Generic lab abbreviations / cell-TYPE terms / stains that collide with obscure short register
# keys. Matching one of these as a misidentified LINE is a false accusation ("AO" = acridine orange,
# "EPC" = endothelial progenitor cells, "OE" = overexpression, "MS"/"SC"/"CO"/"NCI"), so the
# deterministic gate declines to FAIL on them — trading a catch on a handful of ultra-obscure lines
# for never confidently accusing a clean one. (Specificity beats completeness for a trust-the-cite tool.)
_GENERIC_TOKENS = frozenset({"ao", "oe", "of", "ms", "sc", "co", "epc", "nci"})


def _match_iclac_token(t: str, reg: dict, sq: dict, min_len: int) -> dict | None:
    """Match one candidate token against the register. `min_len` is the shortest squashed form we
    trust at this path: 1 for the whole designation as written (a bare 'KB'/'FL' is a real line),
    3 for leading-token prefixes reduced from a descriptor phrase (higher collision risk)."""
    t = t.strip()
    s = _squash(t)
    if not s or s in _GENERIC_TOKENS or len(s) < min_len:
        return None
    if _norm(t) in reg:
        return reg[_norm(t)]
    if len(s) >= 3 and s in sq:
        return sq[s]
    return None


def _iclac_lookup(name: str) -> dict | None:
    """Robust match: extractors often return 'GR-M pancreatic carcinoma line' or 'SNB19'.
    Match the designation as written first (a short whole-string name like 'KB'/'FL' is a real
    misidentified line), then leading-token prefixes of a descriptor phrase. Prefix fragments and the
    squashed form are only trusted at >=3 chars — and generic lab abbreviations are declined — so the
    gate does not over-fire on 2-char / cell-TYPE collisions (see _GENERIC_TOKENS, _match_iclac_token)."""
    reg, sq = _load_iclac(), _load_iclac_squash()
    cand = re.sub(r"\(.*?\)", " ", name).strip()
    toks = [t for t in re.split(r"\s+", cand) if t]
    for t in (name, cand):  # the designation as written — a 2-char whole name may be a real line
        rec = _match_iclac_token(t, reg, sq, min_len=1)
        if rec:
            return rec
    for i in range(min(4, len(toks)), 0, -1):  # leading-token prefixes — reductions, require >=3
        rec = _match_iclac_token(" ".join(toks[:i]), reg, sq, min_len=3)
        if rec:
            return rec
    return None


@dataclass
class Finding:
    item: str            # e.g. "cell line: GR-M"
    kind: str            # "cell_line" | "antibody" | "knockout" | "software" | "rigor"
    result: str          # "FAIL" | "PASS" | "INSUFFICIENT"
    detail: str          # human-readable verdict
    evidence: str = ""   # verbatim phrase from the manuscript
    citation: str = ""   # e.g. "ICLAC-00010 · CVCL_0372"
    method: str = "rule"  # "rule" (deterministic lookup) | "model judgment"


# Descriptor / generic words that carry no cell-line identity. If a name is only these (or empty),
# there is nothing to check — the gate must abstain rather than assert a PASS on an unknown line.
_CL_DESCRIPTORS = frozenset({"cell", "cells", "line", "lines", "the", "a", "an", "primary", "our",
                             "lab", "isolate", "isolated", "culture", "cultured", "cellline"})


def _has_designation(name: str) -> bool:
    """True if `name` carries at least one token that is not a pure descriptor/generic word."""
    return any(_squash(t) and _squash(t) not in _CL_DESCRIPTORS
               for t in re.split(r"\s+", _norm(name)) if t)


def check_cell_line(name: str, evidence: str = "") -> Finding:
    """Deterministic: is this line on the ICLAC misidentified register? A FAIL is citable.
    A missing / descriptor-only name abstains (INSUFFICIENT) — never a PASS on an unidentifiable line."""
    if not _has_designation(name):
        return Finding(
            item=f"cell line: {name.strip() or '(unnamed)'}", kind="cell_line", result="INSUFFICIENT",
            detail=("No identifiable cell-line designation was extracted — name the line so it can be "
                    "checked against the register (and STR-authenticate before use)."),
            evidence=evidence, citation="", method="rule")
    rec = _iclac_lookup(name)
    if rec:
        return Finding(
            item=f"cell line: {name}", kind="cell_line", result="FAIL",
            detail=(f"On the ICLAC Register of Misidentified Cell Lines — claimed "
                    f"{rec['claimed_origin'] or 'unspecified origin'}, actually **{rec['true_identity']}**. "
                    f"Authenticate by STR before use."),
            evidence=evidence, citation=f"{rec['iclac_id']} · {rec['cvcl']}", method="rule")
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


def _ab(label: str, result: str, detail: str, evidence: str, citation: str = "", method: str = "rule") -> Finding:
    return Finding(item=f"antibody: {label}", kind="antibody", result=result, detail=detail,
                   evidence=evidence, citation=citation, method=method)


def check_antibody(name: str, vendor: str = "", catalog: str = "", evidence: str = "") -> Finding:
    """Resolve a catalog number to an RRID via the Antibody Registry — a live best-effort search.

    We cite a PASS only when a returned record's catalog number MATCHES the queried catalog (and the
    vendor, when one is given), so we never cite a different vendor's RRID for the same number. A bare
    name, an ambiguous multi-vendor match, no match, or an unreachable registry all yield
    NEEDS-VERIFICATION — never a guessed PASS. (The one place this differs from the deterministic ICLAC
    gate: the search is a live network call, so it is best-effort, not offline-deterministic.)
    """
    label = (name or f"{vendor} {catalog}").strip()
    if not catalog.strip():
        # Deterministic: no catalog # -> nothing to resolve against the registry -> abstain (rule).
        return _ab(label, "INSUFFICIENT", "No catalog number given — a name alone can't be authenticated; "
                   "add the vendor catalog # and its RRID.", evidence)
    cached = _ab_cache().get(_squash(catalog))
    try:
        if cached is not None:
            items = cached
        else:
            url = "https://www.antibodyregistry.org/api/fts-antibodies?" + urllib.parse.urlencode(
                {"q": catalog, "page": 1, "size": 10})
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
                items = json.loads(resp.read()).get("items", [])
    except Exception:  # noqa: BLE001
        return _ab(label, "INSUFFICIENT", "Could not reach the Antibody Registry — verify the RRID manually.",
                   evidence)
    # keep only records whose catalog number matches what was written, then disambiguate by vendor
    cand = [it for it in items if _squash(str(it.get("catalogNum", ""))) == _squash(catalog)]
    if vendor.strip():
        v = _norm(vendor)
        vend = [it for it in cand if v in _norm(str(it.get("vendorName", "")))]
        if vend:
            cand = vend
        else:
            # A vendor was named but matches NONE of the catalog-matching records. Do not fall
            # through and cite a different vendor's RRID as a PASS — abstain. (A mis-attributed
            # vendor for a real catalog number is exactly the error this tool exists to catch.)
            return _ab(label, "INSUFFICIENT",
                       f"Catalog #{catalog} is registered, but not under the stated vendor "
                       f"({vendor.strip()}) — verify the vendor/catalog pairing and its RRID.",
                       evidence)
    if not cand:
        return _ab(label, "INSUFFICIENT", "No RRID resolves for this exact catalog number — verify it is registered.",
                   evidence)
    if len(cand) > 1 and not vendor.strip():
        return _ab(label, "INSUFFICIENT", "Multiple vendors list this catalog number — specify the vendor "
                   "so the RRID is unambiguous.", evidence)
    it = cand[0]
    rrid = f"RRID:AB_{it.get('accession')}"
    return _ab(label, "PASS", f"Resolves to {rrid} ({it.get('vendorName','')} {it.get('catalogNum','')}).".strip(),
               evidence, citation=rrid)


# ---------------------------------------------------------------------------
# SciCrunch RRID resolver — research software / tools -> RRID:SCR_xxxxxxx.
# A tool is never "misidentified" (no FAIL): it either resolves to a citable RRID (PASS) or has no /
# an unresolvable RRID (NEEDS-VERIFICATION). Like the antibody gate, this is a live network lookup.
# ---------------------------------------------------------------------------
_SCR_RE = re.compile(r"SCR_\d+", re.IGNORECASE)


def _sw(label: str, result: str, detail: str, evidence: str, citation: str = "") -> Finding:
    return Finding(item=f"software: {label}", kind="software", result=result, detail=detail,
                   evidence=evidence, citation=citation, method="rule")


def check_software(name: str, rrid: str = "", evidence: str = "") -> Finding:
    """Resolve a research-tool RRID (RRID:SCR_xxxxxxx) against the SciCrunch resolver — best-effort.

    Software identity is a citation-completeness check, so there is no FAIL: a tool either cites a real
    registered record (PASS) or it does not (NEEDS-VERIFICATION). A bare tool name with no RRID, an
    unresolvable RRID, or an unreachable resolver all abstain — never a guessed PASS. The SCR id may be
    in the extracted `rrid` field or embedded in the evidence phrase, so we look in both.
    """
    label = (name or "software tool").strip()
    m = _SCR_RE.search(rrid or "") or _SCR_RE.search(evidence or "")
    if not m:
        return _sw(label, "INSUFFICIENT",
                   "No RRID given for this tool — add its Research Resource Identifier "
                   "(RRID:SCR_xxxxxxx) so the exact software can be cited.", evidence)
    scr = "SCR_" + m.group(0).split("_", 1)[1]
    try:
        url = f"https://scicrunch.org/resolver/RRID:{scr}.json"
        # SciCrunch's WAF 403s the default Python-urllib User-Agent — send a browser UA (public
        # JSON endpoint, no key required).
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read())
    except Exception:  # noqa: BLE001
        return _sw(label, "INSUFFICIENT",
                   f"Could not reach the SciCrunch resolver to confirm RRID:{scr} — verify it manually.",
                   evidence)
    hits = ((data or {}).get("hits", {}) or {}).get("hits", [])
    resolved = (hits[0].get("_source", {}).get("item", {}).get("name", "") if hits else "")
    if not resolved:
        return _sw(label, "INSUFFICIENT",
                   f"RRID:{scr} does not resolve to a registered tool — verify the identifier.", evidence)
    return _sw(label, "PASS", f"Resolves to RRID:{scr} ({resolved}).", evidence, citation=f"RRID:{scr}")


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
            "software": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string", "description": "the software/analysis tool name ONLY, e.g. "
                         "'ImageJ', 'GraphPad Prism', 'FlowJo', 'CellProfiler'"},
                "rrid": {"type": "string", "description": "its RRID exactly as written, e.g. "
                         "'RRID:SCR_003070' — empty string if none is given"},
                "evidence": {"type": "string", "description": "verbatim phrase"}}, "required": ["name"]}},
            "rigor": {"type": "object", "properties": {
                "sex_reported": {"type": ["boolean", "null"]},
                "n_per_group_stated": {"type": ["boolean", "null"]},
                "randomization_stated": {"type": ["boolean", "null"]},
                "blinding_stated": {"type": ["boolean", "null"]},
                "evidence": {"type": "string"}}},
        },
        "required": ["cell_lines", "antibodies", "software", "rigor"],
    },
}
_EXTRACT_SYSTEM = (
    "You extract ONLY what is explicitly written in a manuscript Methods/Key-Resources section into a "
    "structured resource inventory. Put the verbatim phrase in each 'evidence' field. Methods often list "
    "resources as a Key-Resources / reagent TABLE flattened into running text — rows like "
    "'HeLa ATCC Cat# CCL-2 RRID:CVCL_0030' or 'A549 ATCC CCL-185' — as well as in ordinary prose; extract "
    "every cell line and antibody from BOTH the tables and the prose. Extract every named research "
    "software or analysis tool (e.g. ImageJ, GraphPad Prism, FlowJo, CellProfiler) into 'software', with "
    "any 'RRID:SCR_' identifier written for it (empty string if none). For rigor flags, set true only if "
    "the fact is explicitly stated, false if the section clearly omits it, null if there is no basis to "
    "judge. Never infer identities, catalog numbers, or RRIDs.")


def extract_resources(methods_text: str) -> dict:
    # call_tool RAISES when the model emits no tool_use block (parse.call_tool) or the Anthropic API
    # errors (429/529/network). It can ALSO, non-deterministically, emit an all-empty extraction on a
    # resource-dense Methods (e.g. a flattened Key-Resources table). So retry on an exception AND on an
    # empty result over substantial text, then fall back to an empty extraction so review() degrades to
    # a "no resources found" report instead of crashing (502) on a live paste.
    substantial = len(methods_text.strip()) > 400
    fallback = {"cell_lines": [], "antibodies": [], "software": [], "rigor": {}}
    for _ in range(3):
        try:
            d = call_tool(_EXTRACT_SYSTEM, f"Methods:\n\n{methods_text}", _EXTRACT_TOOL, max_tokens=2048)
        except Exception:  # noqa: BLE001 — any extraction failure degrades, never propagates
            continue
        if isinstance(d, dict):
            if not substantial or d.get("cell_lines") or d.get("antibodies") or d.get("software"):
                return d
            fallback = d  # substantial text but nothing came back — retry; keep the last as fallback
    return fallback


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
    # The headline verdict is issued by the DETERMINISTIC (rule) gates only — a deterministic FAIL
    # (a cell line on the register, a catalog#/vendor mismatch) is "Needs fixes". A model-judgment
    # finding (rigor presence, knockout-control reasoning) can only ask for a human check, never
    # fabricate the deterministic failure — it degrades to "Needs verification".
    if any(f.result == "FAIL" and f.method == "rule" for f in findings):
        return "Needs fixes"
    if any(f.result in ("FAIL", "INSUFFICIENT") for f in findings):
        return "Needs verification"
    return "Submission-ready"


def run_gates(res: dict, methods_text: str) -> ReproReport:
    """Run the deterministic gates + the knockout-reasoning gate over an ALREADY-extracted resource
    dict, and roll up the report. Split out from review() so whole-manuscript review can extract across
    chunks, merge the resources, and gate the merged set once (see verdict/manuscript.py) — the gate
    logic and its honest rule/model-judgment labelling stay in exactly one place."""
    findings: list[Finding] = []
    for cl in res.get("cell_lines", []):
        findings.append(check_cell_line(cl.get("name", ""), cl.get("evidence", "")))
    for ab in res.get("antibodies", []):
        name = ab.get("name", "")
        findings.append(check_antibody(name, ab.get("vendor", ""),
                                       ab.get("catalog", ""), ab.get("evidence", "")))
        # The ONE reasoning gate: did the paper validate THIS antibody with a genetic control?
        # A labelled model judgment (PASS / INSUFFICIENT), never a deterministic FAIL.
        if name.strip():
            kf = assess_knockout_control(methods_text, name)
            findings.append(Finding(item=f"antibody validation: {name}", kind="knockout",
                                    result=kf.result, detail=kf.detail, evidence=kf.evidence,
                                    method=kf.method))
    for sw in res.get("software", []):
        findings.append(check_software(sw.get("name", ""), sw.get("rrid", ""), sw.get("evidence", "")))
    findings += rigor_findings(res.get("rigor", {}))
    verdict = aggregate(findings)
    to_fix = [f"{f.item} — {f.detail}" for f in findings if f.result in ("FAIL", "INSUFFICIENT")]
    return ReproReport(
        findings=findings, verdict=verdict,
        n_fail=sum(1 for f in findings if f.result == "FAIL"),
        n_pass=sum(1 for f in findings if f.result == "PASS"),
        n_insufficient=sum(1 for f in findings if f.result == "INSUFFICIENT"),
        to_fix=to_fix)


def review(methods_text: str) -> ReproReport:
    """End-to-end: Methods text -> extracted resources -> deterministic gates -> report."""
    return run_gates(extract_resources(methods_text), methods_text)


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
