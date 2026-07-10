"""Patient <-> clinical-trial eligibility matching. Claude extracts; deterministic code decides."""
from __future__ import annotations
from dataclasses import dataclass, field

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
