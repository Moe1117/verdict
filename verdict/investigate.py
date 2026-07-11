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


def _strip_tags(xml: str) -> str:
    """PMC full text arrives as JATS XML; hand Claude readable text (tags removed, whitespace collapsed)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()

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


def _canon_id(raw: str) -> str:
    """Canonicalize an id to the form the retrieval log stores: models emit PMIDs bare / spaced /
    URL-wrapped and CVCLs in mixed case. Check CVCL/RRID before the digit fallback (a CVCL has digits)."""
    s = str(raw).strip()
    m = re.search(r"PMID[:\s]*(\d+)", s, re.I)  # explicit PMID prefix, any length
    if m:
        return "PMID:" + m.group(1)
    m = re.search(r"CVCL[_ ]?([0-9A-Za-z]+)", s, re.I)
    if m:
        return "CVCL_" + m.group(1)
    m = re.search(r"\bAB[_ ]?(\d[0-9A-Za-z]*)", s, re.I)
    if m:
        return "RRID:AB_" + m.group(1)
    m = re.search(r"\b(\d{5,9})\b", s)  # a bare PubMed id (no prefix)
    if m:
        return "PMID:" + m.group(1)
    return s


def _kind_of(cid: str) -> str:
    if cid.startswith("PMID:"):
        return "pubmed"
    if cid.startswith("CVCL_"):
        return "cellosaurus"
    if cid.startswith("RRID:"):
        return "antibody_registry"
    return "misc"


def verify_citations(inv: Investigation, retrieved: set) -> Investigation:
    """Deterministic grounding gate: canonicalize each citation id, keep only those actually retrieved
    by a tool, re-derive their kind, and downgrade an ungrounded 'found' verdict to abstain. Fabricated
    citations cannot survive this."""
    kept = []
    for c in inv.cited:
        cid = _canon_id(c.id)
        if cid in retrieved:
            c.id, c.kind = cid, _kind_of(cid)
            kept.append(c)
    inv.cited = kept
    inv.grounded = bool(kept)
    has_pubmed = any(c.kind == "pubmed" for c in kept)
    if inv.kind == "antibody" and inv.verdict == _ANTIBODY_FOUND and not has_pubmed:
        inv.verdict = _ANTIBODY_NONE
    if inv.kind == "cell_line" and inv.verdict == _CELL_FULL and not has_pubmed:
        inv.verdict = _CELL_PARTIAL  # the CVCL may still be grounded, but the primary reference is not
    return inv


def _iclac_cvcl(name: str) -> str:
    """Resolve a cell-line NAME to its CVCL via the bundled ICLAC misidentified-line register
    (Cellosaurus REST 404s on names — it needs the CVCL). '' if not a known misidentified line."""
    try:
        from .repro import _iclac_lookup
        rec = _iclac_lookup(name)
        return rec.get("cvcl", "") if rec else ""
    except Exception:  # noqa: BLE001
        return ""


class Retriever:
    """Real retrieval over public APIs. Every id it returns is logged in `retrieved` — the ground truth
    the citation-verification gate checks against. All methods degrade to empty on any error."""

    def __init__(self, email: str = ""):
        self.email = email or os.getenv("NCBI_EMAIL", "")
        self.retrieved: set = set()
        self.n_search = 0
        self.n_fetch = 0
        self.n_pmc = 0

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

    def pmc_fetch(self, pmids: list) -> dict:
        """Escalate to PMC OPEN-ACCESS full text for candidate PMIDs — antibody genetic-validation
        usually lives in the Methods, not the abstract. Map each PMID -> its PMC id (elink), fetch the
        OA full text (efetch db=pmc), strip JATS tags, and log the PMID ONLY when full text was actually
        retrieved. Non-OA records or any error degrade to empty. Citations stay keyed to the PMID, so the
        deterministic grounding gate is unchanged."""
        self.n_pmc += 1
        out: dict = {}
        for pid in [str(p).replace("PMID:", "").strip() for p in pmids][:3]:
            if not pid:
                continue
            try:
                link = json.loads(self._eutil("elink.fcgi", {
                    "dbfrom": "pubmed", "db": "pmc", "id": pid, "retmode": "json"}))
                pmcids = [lk for ls in link.get("linksets", [])
                          for db in ls.get("linksetdbs", []) if db.get("dbto") == "pmc"
                          for lk in db.get("links", [])]
                if not pmcids:
                    continue
                text = _strip_tags(self._eutil("efetch.fcgi", {
                    "db": "pmc", "id": str(pmcids[0]), "retmode": "xml"}))
                if text:
                    out[pid] = text[:6000]
                    self.retrieved.add(f"PMID:{pid}")
            except Exception:  # noqa: BLE001
                continue
        return out

    def _cello_fetch(self, ident: str) -> dict:
        """Fetch + parse one Cellosaurus record by identifier (CVCL or, where supported, name); log its
        CVCL + reference PMIDs. Empty on any error."""
        try:
            body = _http_get(f"{_CELLO}/cell-line/{urllib.parse.quote(ident)}?format=json")
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

    def cellosaurus_lookup(self, name_or_cvcl: str) -> dict:
        """Look up a cell line and log its CVCL + reference PMIDs. Cellosaurus REST 404s on cell-line
        NAMES (it needs the CVCL), so if a name lookup finds nothing, resolve the name to its CVCL via
        the bundled ICLAC register — the same citable source the deterministic gate uses — and fetch the
        real record by CVCL. This makes the ICLAC -> CVCL -> reference provenance chain robust."""
        rec = self._cello_fetch(name_or_cvcl)
        if not rec and not name_or_cvcl.strip().upper().startswith("CVCL"):
            cvcl = _iclac_cvcl(name_or_cvcl)
            if cvcl:
                rec = self._cello_fetch(cvcl)
        return rec


# ---------------------------------------------------------------------------
# The bounded agentic loop — Claude drives; the retrieval log decides what may be cited.
# ---------------------------------------------------------------------------
_TOOLS = [
    {"name": "pubmed_search", "description": "Search PubMed; returns real PMIDs.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "pubmed_fetch", "description": "Fetch title+abstract text for PMIDs you already found.",
     "input_schema": {"type": "object", "properties": {
         "pmids": {"type": "array", "items": {"type": "string"}}}, "required": ["pmids"]}},
    {"name": "pmc_fetch",
     "description": "Fetch PMC OPEN-ACCESS FULL TEXT for PMIDs you already found. Use when the abstract is "
                    "promising but doesn't confirm a genetic (knockout/knockdown/CRISPR/siRNA) validation — "
                    "that evidence usually lives in the Methods full text, not the abstract.",
     "input_schema": {"type": "object", "properties": {
         "pmids": {"type": "array", "items": {"type": "string"}}}, "required": ["pmids"]}},
    {"name": "cellosaurus_lookup", "description": "Look up a cell line in Cellosaurus by name or CVCL id.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "emit_investigation",
     "description": "Finish: emit your grounded verdict. ONLY cite ids the tools returned to you.",
     "input_schema": {"type": "object", "properties": {
         "verdict": {"type": "string",
                     "enum": [_ANTIBODY_FOUND, _ANTIBODY_NONE, _CELL_FULL, _CELL_PARTIAL, _INCONCLUSIVE]},
         "reasoning": {"type": "string"},
         "cited": {"type": "array", "items": {"type": "object", "properties": {
             "id": {"type": "string"}, "kind": {"type": "string"},
             "title": {"type": "string"}, "why": {"type": "string"}}, "required": ["id", "kind"]}},
         "steps": {"type": "array", "items": {"type": "string"}}},
         "required": ["verdict", "reasoning", "cited", "steps"]}},
]

_SYSTEM = ("You are a research-integrity investigator. Use the tools to find REAL evidence, then call "
           "emit_investigation. NEVER cite a PMID or CVCL the tools did not return to you. If you cannot "
           "find genuine evidence, emit the abstain verdict. When an abstract is promising but does not "
           "confirm a genetic (knockout/knockdown/CRISPR/siRNA) validation, escalate with pmc_fetch to read "
           "the open-access full text before deciding. Be efficient: a few targeted searches, decide.")


def _dispatch(retriever: "Retriever", name: str, args: dict, caps: dict) -> str:
    if name == "pubmed_search" and retriever.n_search < caps["search"]:
        return json.dumps({"pmids": retriever.pubmed_search(args.get("query", ""))})
    if name == "pubmed_fetch" and retriever.n_fetch < caps["fetch"]:
        return json.dumps(retriever.pubmed_fetch(args.get("pmids", [])))
    if name == "pmc_fetch" and retriever.n_pmc < caps.get("pmc", 3):
        return json.dumps(retriever.pmc_fetch(args.get("pmids", [])))
    if name == "cellosaurus_lookup":
        return json.dumps(retriever.cellosaurus_lookup(args.get("name", "")))
    return json.dumps({"error": "tool budget exhausted — call emit_investigation now"})


def _build_investigation(d: dict, kind: str) -> Investigation:
    """Assemble an Investigation from an emit_investigation tool input (used by both the normal emit and
    the forced final turn)."""
    return Investigation(
        kind=kind, verdict=d.get("verdict", _INCONCLUSIVE),
        cited=[Citation(**{k: c.get(k, "") for k in ("id", "kind", "title", "why")})
               for c in d.get("cited", [])],
        reasoning=d.get("reasoning", ""), steps=list(d.get("steps", [])))


def _force_emit(client, messages: list, kind: str) -> "Investigation | None":
    """Final turn: FORCE emit_investigation so a loop that gathered real evidence concludes from what it
    has, instead of discarding it as INCONCLUSIVE because it ran out of steps. Returns None if even the
    forced call yields no verdict (the caller then degrades to INCONCLUSIVE). The forced verdict still
    passes through the deterministic grounding gate downstream — forcing a conclusion never forces a
    citation."""
    from .parse import model
    try:
        msg = client.messages.create(model=model(), max_tokens=1200, system=_SYSTEM, tools=_TOOLS,
                                     tool_choice={"type": "tool", "name": "emit_investigation"},
                                     messages=messages)
        emit = next((b for b in msg.content
                     if getattr(b, "type", "") == "tool_use" and b.name == "emit_investigation"), None)
        return _build_investigation(dict(emit.input), kind) if emit else None
    except Exception:  # noqa: BLE001
        return None


def run_investigation(task: str, retriever: "Retriever", client=None, kind: str = "antibody",
                      max_steps: int = 14, caps: dict | None = None) -> Investigation:
    """Run the bounded Claude tool-use loop against real APIs, then verify citations. If the loop runs
    out of steps without a verdict, force a final grounded conclusion from the evidence gathered.
    Degrades to INCONCLUSIVE on any failure — never raises."""
    caps = caps or {"search": 3, "fetch": 6, "pmc": 3}
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    from .parse import model
    messages = [{"role": "user", "content": task}]
    try:
        for _ in range(max_steps):
            msg = client.messages.create(model=model(), max_tokens=1200, system=_SYSTEM,
                                         tools=_TOOLS, messages=messages)
            uses = [b for b in msg.content if getattr(b, "type", "") == "tool_use"]
            if not uses:
                break
            emit = next((b for b in uses if b.name == "emit_investigation"), None)
            if emit:
                return verify_citations(_build_investigation(dict(emit.input), kind), retriever.retrieved)
            messages.append({"role": "assistant", "content": [
                {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input} for b in uses]})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b.id,
                 "content": _dispatch(retriever, b.name, dict(b.input), caps)} for b in uses]})
        # Ran out of steps (or the model stopped calling tools) without a verdict: force a final grounded
        # conclusion from what was retrieved, rather than throwing the evidence away as INCONCLUSIVE.
        forced = _force_emit(client, messages, kind)
        if forced is not None:
            return verify_citations(forced, retriever.retrieved)
    except Exception:  # noqa: BLE001 — any API/tool failure degrades, never crashes
        pass
    return Investigation(kind=kind, verdict=_INCONCLUSIVE,
                         reasoning="investigation did not complete", steps=["investigation incomplete"])


# ---------------------------------------------------------------------------
# Entrypoints.
# ---------------------------------------------------------------------------
def investigate_antibody(name: str, target: str = "", catalog: str = "", rrid: str = "") -> Investigation:
    """Agentically search the literature for whether `name` was ever knockout/knockdown-validated."""
    extras = "".join(x for x in (f", target {target}" if target else "",
                                 f", catalog {catalog}" if catalog else "",
                                 f", {rrid}" if rrid else "") if x)
    task = (f"Investigate whether the antibody '{name}'{extras} has ever been validated for specificity "
            "with a GENETIC control (knockout/knockdown/CRISPR/siRNA showing signal loss) in the published "
            "literature. Search PubMed (by target + 'knockout'/'validation'/'specificity'), read the most "
            "relevant abstracts, and emit FOUND_VALIDATION with the real PMID if you find one, else "
            "NO_VALIDATION_FOUND.")
    return run_investigation(task, Retriever(), kind="antibody")


def investigate_cell_line(name: str, iclac_id: str = "", cvcl: str = "") -> Investigation:
    """Agentically build the misidentification provenance chain (Cellosaurus CVCL + primary PMID)."""
    extras = "".join(x for x in (f", ICLAC {iclac_id}" if iclac_id else "",
                                 f", {cvcl}" if cvcl else "") if x)
    task = (f"Build the misidentification provenance chain for the cell line '{name}'{extras}. Look it up "
            "in Cellosaurus to confirm the CVCL and the documented problem, then search PubMed for the "
            "primary reference that first reported the misidentification. Emit PROVENANCE_CHAIN citing the "
            "real CVCL and the real primary-reference PMID, or PARTIAL if you can only ground part of the chain.")
    return run_investigation(task, Retriever(), kind="cell_line")
