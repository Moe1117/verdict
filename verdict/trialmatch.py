"""Patient <-> clinical-trial eligibility matching. Claude extracts; deterministic code decides."""
from __future__ import annotations

import json
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
    ctype: str = ""           # "structured" (rule) | "semantic" (model judgment) — for the UI tag

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
    """Pure parser: tool-call payload -> list[Criterion]. No LLM call here.

    Defensive against an observed model quirk: for some inputs the tool call comes back
    with `criteria` as a JSON-encoded *string* (occasionally double-wrapped as another
    `{"criteria": [...]}` object) instead of a native array, even though the declared
    input_schema types it as an array. Recover by decoding the string before iterating,
    rather than raising downstream on `c["id"]` against a string index.
    """
    raw = d.get("criteria", [])
    if isinstance(raw, str):
        parsed = json.loads(raw)
        raw = parsed.get("criteria", []) if isinstance(parsed, dict) else parsed
    out: list[Criterion] = []
    for c in raw:
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
    """Claude tool-use call: trial eligibility text -> list[Criterion]. Requires ANTHROPIC_API_KEY.

    max_tokens=8000: observed in the wild (real CT.gov trials) that dense eligibility text
    (10k+ chars, 20+ lettered sub-criteria) can truncate a 3000-token tool-use response
    mid-JSON, which silently yields an empty `{}` payload -> zero criteria for a trial that
    actually has many. 8000 covers the longest real eligibility blocks seen so far.
    """
    d = call_tool(_CRITERIA_SYSTEM, f"Eligibility text:\n\n{eligibility_text}",
                  _CRITERIA_TOOL, max_tokens=8000)
    return criteria_from_json(d)


_SEMANTIC_TOOL = {
    "name": "judge",
    "description": "Decide if the patient meets ONE criterion.",
    "input_schema": {
        "type": "object",
        "properties": {
            "result": {"enum": ["MET", "NOT_MET", "INSUFFICIENT"]},
            "evidence_phrase": {"type": "string"},  # verbatim note phrase or "not stated"
            "note": {"type": "string"}, "confidence": {"enum": ["high", "medium", "low"]},
        },
        "required": ["result", "evidence_phrase", "note", "confidence"],
    },
}

_SEMANTIC_SYSTEM = (
    "Decide ONLY from the patient note whether the patient meets this trial criterion. "
    "If the note does not clearly state the needed fact, answer INSUFFICIENT — never guess."
)


def judge_semantic(crit: Criterion, p: PatientProfile) -> tuple[str, str, str, str]:
    """Claude judge for a semantic (non-structured) criterion. Biased to abstain: when the
    patient note doesn't clearly state the needed fact, the model is instructed to answer
    INSUFFICIENT rather than guess. Returns (result, evidence_phrase, note, confidence).
    Requires ANTHROPIC_API_KEY."""
    user = (f"CRITERION ({crit.kind}): {crit.predicate}\nSOURCE: {crit.source_text}\n\n"
            f"PATIENT NOTE:\n{p.raw_note}")
    d = call_tool(_SEMANTIC_SYSTEM, user, _SEMANTIC_TOOL, max_tokens=512)
    return (d["result"], d.get("evidence_phrase", "not stated"), d.get("note", ""),
            d.get("confidence", "low"))


def match(p: PatientProfile, nct_id: str, title: str, status: str,
          crits: list[Criterion]) -> TrialCard:
    """Per-trial orchestration: run every criterion (structured via the pure comparator,
    semantic via the Claude judge), then hand the results to the pure aggregate() for the verdict."""
    results: list[CriterionResult] = []
    for c in crits:
        if c.ctype == "structured":
            res, phrase, note = eval_structured(c, p)
            conf = "high" if res != "INSUFFICIENT" else "low"
        else:
            res, phrase, note, conf = judge_semantic(c, p)
        results.append(CriterionResult(c.id, c.kind, res, conf, phrase, note,
                                       c.predicate, c.source_text, c.ctype))
    verdict = aggregate(results)
    to_verify = [f"Confirm: {r.predicate}" for r in results if r.result == "INSUFFICIENT"]
    n_met = sum(1 for r in results if r.result == "MET")
    n_disq = sum(1 for r in results
                 if (r.kind == "exclusion" and r.result == "MET")
                 or (r.kind == "inclusion" and r.result == "NOT_MET"))
    return TrialCard(nct_id, title, status,
                     f"https://clinicaltrials.gov/study/{nct_id}", verdict, results,
                     to_verify, n_met, n_disq, len(to_verify))


_RANK = {"Likely eligible": 0, "Needs verification": 1, "Ineligible": 2}


def rank_cards(cards: list[TrialCard]) -> list[TrialCard]:
    """Eligible trials first, then fewest open (to-verify) items within each verdict bucket."""
    return sorted(cards, key=lambda c: (_RANK.get(c.verdict, 3), c.n_to_verify))


def card_to_dict(c: TrialCard) -> dict:
    """JSON-safe serialization of a TrialCard for the API/UI layer."""
    return asdict(c)


# Below this length, a genuinely trivial trial can legitimately have zero extracted
# criteria (e.g. "see protocol" placeholder text). Above it, zero criteria almost always
# means extraction failed (usually a truncated tool-use response on unusually dense,
# deeply-nested eligibility text) rather than that the trial truly has no criteria.
_MIN_ELIGIBILITY_LEN_FOR_NONEMPTY_CRITERIA = 200


def review(note: str, condition: str | None = None, max_trials: int = 5) -> list[TrialCard]:
    """End-to-end: note -> profile -> candidate trials -> per-criterion match -> ranked cards.

    Skips (does not fabricate a card for) any candidate trial whose criteria extraction
    comes back empty despite substantial eligibility text — that is an extraction failure,
    not a trial with no criteria, and silently emitting a "Needs verification" card with
    zero criteria would misrepresent an unresolved trial as one with nothing to check.
    """
    profile = extract_profile(note)
    cond = condition or profile.diagnosis or ""
    cards: list[TrialCard] = []
    for cand in _trials.search_candidates_by_condition(cond, page_size=max_trials):
        elig = _trials.get_eligibility(cand.nct_id)
        crits = extract_criteria(elig.text)
        if not crits and len(elig.text) >= _MIN_ELIGIBILITY_LEN_FOR_NONEMPTY_CRITERIA:
            continue
        cards.append(match(profile, cand.nct_id, cand.title, cand.status, crits))
    return rank_cards(cards)
