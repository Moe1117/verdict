"""Patient <-> clinical-trial eligibility matching. Claude extracts; deterministic code decides."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .parse import call_tool
from . import trials as _trials

@dataclass
class PatientProfile:
    age: int | None = None
    age_src: str = ""
    sex: str | None = None                 # "MALE" | "FEMALE" | None
    sex_src: str = ""
    diagnosis: str | None = None
    diagnosis_src: str = ""
    stage: str | None = None
    biomarkers: list[str] = field(default_factory=list)
    biomarkers_src: str = ""
    prior_therapies: list[str] = field(default_factory=list)
    prior_therapies_src: str = ""
    ecog: int | None = None
    ecog_src: str = ""
    labs: dict[str, float] = field(default_factory=dict)
    comorbidities: list[str] = field(default_factory=list)
    cns_status: str | None = None
    raw_note: str = ""

@dataclass
class Criterion:
    id: str
    kind: str                 # "inclusion" | "exclusion"
    ctype: str                # "structured" | "semantic"
    predicate: str
    source_text: str
    field: str = ""           # structured only: "age" | "ecog" | "sex" | lab name
    op: str = ""              # "range" | "min" | "max" | "presence"
    lo: float | None = None
    hi: float | None = None

@dataclass
class CriterionResult:
    id: str
    kind: str
    result: str               # "MET" | "NOT_MET" | "INSUFFICIENT"
    confidence: str           # "high" | "medium" | "low"
    evidence_phrase: str
    note: str
    predicate: str
    source_text: str

@dataclass
class TrialCard:
    nct_id: str
    title: str
    status: str
    url: str
    verdict: str              # "Likely eligible" | "Ineligible" | "Needs verification"
    criteria: list[CriterionResult]
    to_verify: list[str]
    n_met: int
    n_disqualifying: int
    n_to_verify: int

def aggregate(results: list[CriterionResult]) -> str:
    """Pure, deterministic verdict from per-criterion results. No LLM.

    - any exclusion MET, or any inclusion NOT_MET -> Ineligible (definitive fail)
    - all inclusions MET and all exclusions NOT_MET (nothing unresolved) -> Likely eligible
    - otherwise -> Needs verification
    """
    incl = [r for r in results if r.kind == "inclusion"]
    excl = [r for r in results if r.kind == "exclusion"]
    if not incl and not excl:
        return "Needs verification"
    if any(r.result == "MET" for r in excl) or any(r.result == "NOT_MET" for r in incl):
        return "Ineligible"
    if all(r.result == "MET" for r in incl) and all(r.result == "NOT_MET" for r in excl):
        return "Likely eligible"
    return "Needs verification"

def _profile_value(fieldname: str, p: PatientProfile) -> tuple[float | None, str]:
    if fieldname == "age":
        return (float(p.age) if p.age is not None else None, p.age_src)
    if fieldname == "ecog":
        return (float(p.ecog) if p.ecog is not None else None, p.ecog_src)
    if fieldname in p.labs:
        return (float(p.labs[fieldname]), f"{fieldname} {p.labs[fieldname]}")
    return (None, "")

def eval_structured(crit: Criterion, p: PatientProfile) -> tuple[str, str, str]:
    """Return (result, evidence_phrase, note). result: MET if the patient's value satisfies
    the criterion's stated condition; NOT_MET if it clearly does not; INSUFFICIENT if unknown.
    The inclusion/exclusion meaning is applied later by aggregate()."""
    val, src = _profile_value(crit.field, p)
    if val is None:
        return ("INSUFFICIENT", "not stated", f"{crit.field or 'value'} not found in note")
    ok = True
    if crit.op == "range":
        ok = (crit.lo is None or val >= crit.lo) and (crit.hi is None or val <= crit.hi)
    elif crit.op == "min":
        ok = crit.lo is None or val >= crit.lo
    elif crit.op == "max":
        ok = crit.hi is None or val <= crit.hi
    phrase = src or f"{crit.field}={val}"
    return ("MET" if ok else "NOT_MET", phrase, f"{crit.field}={val} vs [{crit.lo},{crit.hi}]")


def profile_from_json(d: dict, raw_note: str) -> PatientProfile:
    """Pure parser: tool-call payload -> PatientProfile. No LLM call here."""
    return PatientProfile(
        age=d.get("age"), age_src=d.get("age_src", ""), sex=d.get("sex"),
        sex_src=d.get("sex_src", ""), diagnosis=d.get("diagnosis"),
        diagnosis_src=d.get("diagnosis_src", ""), stage=d.get("stage"),
        biomarkers=list(d.get("biomarkers") or []), biomarkers_src=d.get("biomarkers_src", ""),
        prior_therapies=list(d.get("prior_therapies") or []),
        prior_therapies_src=d.get("prior_therapies_src", ""),
        ecog=d.get("ecog"), ecog_src=d.get("ecog_src", ""),
        labs=dict(d.get("labs") or {}), comorbidities=list(d.get("comorbidities") or []),
        cns_status=d.get("cns_status"), raw_note=raw_note)


def criteria_from_json(d: dict) -> list[Criterion]:
    """Pure parser: tool-call payload -> list[Criterion]. No LLM call here."""
    out: list[Criterion] = []
    for c in d.get("criteria", []):
        out.append(Criterion(
            id=c["id"], kind=c["kind"], ctype=c["ctype"], predicate=c["predicate"],
            source_text=c.get("source_text", ""), field=c.get("field", ""),
            op=c.get("op", ""), lo=c.get("lo"), hi=c.get("hi")))
    return out


_PROFILE_TOOL = {
    "name": "emit_profile",
    "description": "Structured patient facts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "age": {"type": ["integer", "null"]}, "age_src": {"type": "string"},
            "sex": {"type": ["string", "null"], "enum": ["MALE", "FEMALE", None]},
            "diagnosis": {"type": ["string", "null"]}, "stage": {"type": ["string", "null"]},
            "biomarkers": {"type": "array", "items": {"type": "string"}},
            "prior_therapies": {"type": "array", "items": {"type": "string"}},
            "ecog": {"type": ["integer", "null"]}, "ecog_src": {"type": "string"},
            "labs": {"type": "object"}, "comorbidities": {"type": "array", "items": {"type": "string"}},
            "cns_status": {"type": ["string", "null"]},
        },
        "required": ["age", "sex", "diagnosis"],
    },
}

_PROFILE_SYSTEM = (
    "You extract ONLY facts explicitly stated in a clinical note into a structured patient "
    "profile for a deterministic eligibility engine. For every field, put the verbatim phrase "
    "in the corresponding *_src field, or leave the field null if not stated. Never infer."
)


def extract_profile(note: str) -> PatientProfile:
    """Claude tool-use call: patient note -> PatientProfile. Requires ANTHROPIC_API_KEY."""
    d = call_tool(_PROFILE_SYSTEM, f"Note:\n\n{note}", _PROFILE_TOOL, max_tokens=1024)
    return profile_from_json(d, raw_note=note)


_CRITERIA_TOOL = {
    "name": "emit_criteria",
    "description": "One entry per eligibility criterion.",
    "input_schema": {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"}, "kind": {"enum": ["inclusion", "exclusion"]},
                        "ctype": {"enum": ["structured", "semantic"]},
                        "predicate": {"type": "string"}, "source_text": {"type": "string"},
                        "field": {"type": "string"}, "op": {"enum": ["range", "min", "max", ""]},
                        "lo": {"type": ["number", "null"]}, "hi": {"type": ["number", "null"]},
                    },
                    "required": ["id", "kind", "ctype", "predicate", "source_text"],
                },
            },
        },
        "required": ["criteria"],
    },
}

_CRITERIA_SYSTEM = (
    "You split a clinical trial's eligibility criteria into one entry each for a deterministic "
    "eligibility engine. Mark ctype='structured' ONLY for age, ECOG, sex, or numeric lab "
    "thresholds (fill field/op/lo/hi); everything else is 'semantic'. Preserve source_text "
    "verbatim."
)


def extract_criteria(eligibility_text: str) -> list[Criterion]:
    """Claude tool-use call: trial eligibility text -> list[Criterion]. Requires ANTHROPIC_API_KEY."""
    d = call_tool(_CRITERIA_SYSTEM, f"Eligibility text:\n\n{eligibility_text}",
                  _CRITERIA_TOOL, max_tokens=3000)
    return criteria_from_json(d)
