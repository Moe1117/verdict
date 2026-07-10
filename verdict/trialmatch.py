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
