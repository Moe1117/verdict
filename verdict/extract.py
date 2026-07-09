"""Study -> one EvidenceRow. The ONLY generative step in the data path.

Claude reads the abstract/record and fills a structured row, judged RELATIVE to the
claim (direction on the claimed outcome, whether the endpoint is a surrogate, whether
the population matches). It never decides the verdict — it only reports what a study
found. Only NLM-safe metadata + short paraphrase are kept; no verbatim full text.
"""
from __future__ import annotations

from .gates import EvidenceRow
from .parse import ClaimTuple, call_tool
from .retrieve import Source

_DESIGNS = ["meta-analysis of rcts", "target-trial emulation", "systematic review", "rct",
            "prospective cohort", "case-control", "cross-sectional", "case report", "preclinical",
            "guideline / regulatory"]

_TOOL = {
    "name": "evidence_row",
    "description": "Structured extraction of ONE study, judged relative to the claim.",
    "input_schema": {
        "type": "object",
        "properties": {
            "design": {"type": "string", "enum": _DESIGNS},
            "direction": {"type": "integer", "enum": [-1, 0, 1],
                          "description": "on the CLAIMED outcome: +1 supports, -1 contradicts, 0 null/no-effect"},
            "population_match": {"type": "boolean", "description": "study population matches the claim's population"},
            "outcome_match": {"type": "boolean",
                              "description": "the study's PRIMARY endpoint IS the claimed outcome; false if it is "
                                             "only a surrogate / different endpoint"},
            "dramatic_effect": {"type": "boolean",
                                "description": "true ONLY for an all-or-none / very-large effect in a fatal disease "
                                               "where single-arm evidence is the accepted standard"},
            "integrity_ok": {"type": "boolean", "description": "false if retracted / withdrawn / under Expression of Concern"},
            "integrity_note": {"type": "string"},
            "n_int": {"type": "integer", "description": "sample size (patients), 0 if unclear"},
            "year": {"type": "integer"},
            "effect_point": {"type": ["number", "null"], "description": "HR/RR/OR/mean-diff point estimate if reported"},
            "ci_low": {"type": ["number", "null"]},
            "ci_high": {"type": ["number", "null"]},
            "effect_scale": {"type": "string", "enum": ["ratio", "mean_diff", "proportion_diff", ""]},
            "sig": {"type": "string", "enum": ["significant", "nonsignificant", "not_reported"]},
            "is_primary": {"type": ["boolean", "null"], "description": "measured the trial's PRIMARY endpoint"},
            "finding": {"type": "string", "description": "one-line finding in your own words (no verbatim abstract)"},
        },
        "required": ["design", "direction", "population_match", "outcome_match", "dramatic_effect",
                     "integrity_ok", "n_int", "year", "sig", "finding"],
    },
}

_SYSTEM = (
    "You extract ONE study into a structured evidence row for a deterministic verdict engine. "
    "You do NOT decide anything — you only report what THIS study found, judged strictly relative "
    "to the claim. Direction is on the CLAIMED outcome. Mark outcome_match=false when the endpoint "
    "is a surrogate for the claimed outcome. Never invent numbers; use 0/not_reported when unclear."
)


def extract_row(source: Source, abstract: str, claim: ClaimTuple) -> EvidenceRow:
    """Claude reads the abstract and returns one EvidenceRow, relative to the claim."""
    user = (f"CLAIM: {claim.agent} — {claim.outcome} in {claim.population}\n\n"
            f"STUDY: {source.title} ({source.journal} {source.year})\n\nABSTRACT:\n{abstract[:6000]}")
    d = call_tool(_SYSTEM, user, _TOOL, max_tokens=1200)
    return EvidenceRow(
        citation=f"{source.title}. {source.journal} {source.year}.",
        # Display id: drop the "NCT:" scheme prefix (the id already reads as an NCT number) and
        # keep "PMID:xxxx" as-is — never double the registry prefix into "NCTNCT...".
        source_id=source.id.replace("NCT:", ""),
        design=d["design"], direction=int(d["direction"]),
        population_match=bool(d["population_match"]), outcome_match=bool(d["outcome_match"]),
        dramatic_effect=bool(d.get("dramatic_effect", False)),
        integrity_ok=bool(d.get("integrity_ok", True)), integrity_note=d.get("integrity_note", ""),
        n_int=int(d.get("n_int", 0) or 0), year=int(d.get("year", 0) or 0),
        finding=d.get("finding", ""),
        effect_point=d.get("effect_point"), ci_low=d.get("ci_low"), ci_high=d.get("ci_high"),
        effect_scale=d.get("effect_scale", "") or "", sig=d.get("sig", "") or "",
        is_primary=d.get("is_primary"),
    )
