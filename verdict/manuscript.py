"""Phase 2 — whole-manuscript ingestion + auto-fix.

The fast /api/repro path grades one pasted Methods paragraph. This module scales that to a whole
manuscript: chunk the text, extract EVERY resource across chunks, dedupe, run the same deterministic
gates once (repro.run_gates), optionally run the agentic investigator on the flagged resources, and
optionally draft submission-ready corrections.

The honesty discipline is unchanged: the gates still issue every headline verdict from citable ground
truth, and auto-fix NEVER invents an identity, catalog #, or RRID — it drafts the corrective ACTION
grounded in the finding's own citation, and every suggestion is LABELLED a draft for human review.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from . import investigate, repro
from .parse import call_tool
from .repro import ReproReport, report_to_dict

# A whole-manuscript resource extraction is one paid Claude call per chunk; investigating each flagged
# resource is a full agentic loop. Bound both so a single /api/review paste can't fan out unbounded spend.
_MAX_INVESTIGATIONS = 3


@dataclass
class Correction:
    """A drafted, submission-ready fix for one flagged finding. Grounded in the finding's citation;
    always a draft, never presented as authoritative."""
    item: str            # which finding this fixes, e.g. "cell line: GR-M"
    original: str        # the verbatim manuscript phrase being corrected ("" if none)
    suggestion: str      # the drafted corrective text
    rationale: str = ""  # why (traces to the gate's deterministic citation)
    label: str = "draft — human review required"


@dataclass
class ManuscriptReport:
    report: ReproReport                          # rolled-up findings + headline verdict (reused gates)
    investigations: list = field(default_factory=list)   # list[Investigation] for flagged resources
    corrections: list = field(default_factory=list)      # list[Correction] (auto-fix drafts)
    n_resources: int = 0
    n_chunks: int = 1


# ---------------------------------------------------------------------------
# Ingestion: chunk a long manuscript, extract per chunk, merge/dedupe resources.
# ---------------------------------------------------------------------------
def _chunk_text(text: str, size: int = 6000, overlap: int = 300) -> list[str]:
    """Split a long manuscript into overlapping windows so each extraction call stays within budget.
    The overlap keeps a resource that straddles a boundary from being lost."""
    text = text.strip()
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    return [text[i:i + size] for i in range(0, len(text), step)]


def _merge_resources(parts: list[dict]) -> dict:
    """Merge per-chunk extractions into one resource set. Dedupe cell lines and software by squashed
    name, antibodies by (squashed name, squashed catalog). Rigor flags roll up as True > False > null:
    a fact reported anywhere in the manuscript counts as reported."""
    cells, seen_c = [], set()
    antibodies, seen_a = [], set()
    software, seen_s = [], set()
    rigor: dict = {}
    for p in parts:
        for cl in p.get("cell_lines", []) or []:
            key = repro._squash(cl.get("name", ""))
            if key and key not in seen_c:
                seen_c.add(key)
                cells.append(cl)
        for ab in p.get("antibodies", []) or []:
            key = (repro._squash(ab.get("name", "")), repro._squash(ab.get("catalog", "")))
            if any(key) and key not in seen_a:
                seen_a.add(key)
                antibodies.append(ab)
        for sw in p.get("software", []) or []:
            key = repro._squash(sw.get("name", ""))
            if key and key not in seen_s:
                seen_s.add(key)
                software.append(sw)
        for k, v in (p.get("rigor", {}) or {}).items():
            if k == "evidence":
                if v and not rigor.get("evidence"):
                    rigor["evidence"] = v
            elif v is True:
                rigor[k] = True
            elif v is False and rigor.get(k) is not True:
                rigor[k] = False
            elif k not in rigor:
                rigor[k] = v
    return {"cell_lines": cells, "antibodies": antibodies, "software": software, "rigor": rigor}


def _investigate_flagged(report: ReproReport, resources: dict, cap: int) -> list:
    """Run the agentic investigator on the resources the gates flagged — cell lines that FAIL the ICLAC
    register (build the provenance chain) and antibodies whose validation was INSUFFICIENT (search for a
    published genetic validation). Bounded by `cap`."""
    out: list = []
    failed_cells = {f.item[len("cell line: "):] for f in report.findings
                    if f.kind == "cell_line" and f.result == "FAIL"}
    for cl in resources.get("cell_lines", []):
        if len(out) >= cap:
            return out
        if cl.get("name", "") in failed_cells:
            out.append(investigate.investigate_cell_line(cl.get("name", "")))
    unvalidated = {f.item[len("antibody validation: "):] for f in report.findings
                   if f.kind == "knockout" and f.result == "INSUFFICIENT"}
    for ab in resources.get("antibodies", []):
        if len(out) >= cap:
            return out
        if ab.get("name", "") in unvalidated:
            out.append(investigate.investigate_antibody(ab.get("name", ""), target=ab.get("name", "")))
    return out


def review_manuscript(text: str, *, extract_fn=None, investigate: bool = False,
                      autofix: bool = False, client=None,
                      max_investigations: int = _MAX_INVESTIGATIONS) -> ManuscriptReport:
    """Whole-manuscript review: chunk -> extract per chunk -> merge -> gate. Optionally investigate the
    flagged resources and/or draft corrections. Reuses repro.run_gates so gate logic lives in one place."""
    extract_fn = extract_fn or repro.extract_resources
    chunks = _chunk_text(text)
    merged = _merge_resources([extract_fn(c) for c in chunks])
    report = repro.run_gates(merged, text)
    n_resources = len(merged["cell_lines"]) + len(merged["antibodies"]) + len(merged["software"])
    investigations = _investigate_flagged(report, merged, max_investigations) if investigate else []
    corrections = draft_corrections(report, text, client=client) if autofix else []
    return ManuscriptReport(report=report, investigations=investigations, corrections=corrections,
                            n_resources=n_resources, n_chunks=len(chunks))


# ---------------------------------------------------------------------------
# Auto-fix: draft submission-ready corrections for the flagged findings.
# ---------------------------------------------------------------------------
_FIX_TOOL = {
    "name": "emit_corrections",
    "description": "Draft a submission-ready correction for each flagged finding.",
    "input_schema": {"type": "object", "properties": {
        "corrections": {"type": "array", "items": {"type": "object", "properties": {
            "item": {"type": "string", "description": "the finding item this corrects, copied verbatim"},
            "suggestion": {"type": "string", "description": "the corrective text the author should add/replace"},
            "rationale": {"type": "string", "description": "one line: why, grounded in the finding's citation"}},
            "required": ["item", "suggestion"]}}},
        "required": ["corrections"]},
}
_FIX_SYSTEM = (
    "You draft submission-ready corrective text for issues already flagged in a manuscript's Methods. Each "
    "finding carries a deterministic verdict and a citation — draft the concrete fix the author should make: "
    "for a misidentified cell line, an STR-authentication sentence stating the true identity from the "
    "citation; for an unauthenticated antibody, add the vendor catalog # and its RRID; for missing antibody "
    "validation, add or cite a genetic knockout/knockdown/CRISPR/siRNA control; for a missing rigor element, "
    "the ARRIVE/MDAR-compliant sentence. NEVER invent an identity, catalog number, RRID, or result — write "
    "the corrective ACTION and leave a clearly-marked <placeholder> for any value the author must supply. "
    "Keep each suggestion to 1–2 sentences — concise and paste-ready. Every suggestion is a draft for human review.")


def draft_corrections(report: ReproReport, manuscript_text: str, *, client=None) -> list[Correction]:
    """One Claude call that drafts a labelled correction per actionable (FAIL/INSUFFICIENT) finding.
    Grounded in each finding's own citation; degrades to [] on any error (never blocks a review)."""
    actionable = [f for f in report.findings if f.result in ("FAIL", "INSUFFICIENT")]
    if not actionable:
        return []
    payload = "\n".join(
        f"- [{f.result}] {f.item}: {f.detail} (citation: {f.citation or 'n/a'}; manuscript text: "
        f"'{f.evidence}')" for f in actionable)
    try:
        d = call_tool(_FIX_SYSTEM, f"Findings to correct:\n{payload}\n\nManuscript:\n{manuscript_text[:4000]}",
                      _FIX_TOOL, max_tokens=3000)
    except Exception:  # noqa: BLE001 — auto-fix is advisory; never block or crash a review
        return []
    corrections = d.get("corrections", [])
    # Some model turns return the array as a stringified JSON blob rather than a structured list — recover
    # the list so a whole review's fixes are not silently dropped (or crashed on when iterating its chars).
    if isinstance(corrections, str):
        try:
            parsed = json.loads(corrections)
            corrections = parsed.get("corrections", []) if isinstance(parsed, dict) else parsed
        except Exception:  # noqa: BLE001
            corrections = []
    if not isinstance(corrections, list):
        corrections = []
    by_item = {f.item: f for f in actionable}
    out: list[Correction] = []
    for c in corrections:
        if not isinstance(c, dict):
            continue
        src = by_item.get(c.get("item", ""))
        out.append(Correction(item=c.get("item", ""), original=(src.evidence if src else ""),
                              suggestion=c.get("suggestion", ""), rationale=c.get("rationale", "")))
    return out


def manuscript_report_to_dict(r: ManuscriptReport) -> dict:
    return {
        "report": report_to_dict(r.report),
        "investigations": [asdict(i) for i in r.investigations],
        "corrections": [asdict(c) for c in r.corrections],
        "n_resources": r.n_resources,
        "n_chunks": r.n_chunks,
    }
