# Trial Eligibility Reviewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Point the Verdict decidable-decision engine at patient↔clinical-trial eligibility: paste a patient note, get ranked recruiting trials each with a per-criterion audit ledger (`MET`/`NOT_MET`/`INSUFFICIENT`), a "to-verify" worklist, and a verdict that is never `Likely eligible` while any criterion is unresolved.

**Architecture:** Claude extracts structured data (the patient note → `PatientProfile`; each trial's eligibility text → `Criterion[]`). Deterministic code makes the calls: structured criteria via pure comparators, semantic criteria via a labelled Claude judgment that biases to abstain, and a **pure aggregator** turns per-criterion results into the verdict. Retrieval is the ClinicalTrials.gov REST v2 API. A frozen deck bulletproofs the demo; a best-effort live lane handles pasted notes.

**Tech Stack:** Python 3 (`dataclasses`, `pytest`), the `anthropic` SDK (already used in `verdict/baseline.py`), `urllib`/`requests` for CT.gov v2, FastAPI (`verdict/webapp.py`), the existing Vite/React UI in `web/`. Run everything with `PYTHONPATH=. .venv/bin/python`.

**Spec:** `docs/superpowers/specs/2026-07-10-trial-eligibility-reviewer-design.md` — read §7 (honesty boundary) before touching semantic matching.

---

## File Structure

- **Create `verdict/trials.py`** — ClinicalTrials.gov REST v2 client. Responsibility: fetch candidate recruiting studies for a `PatientProfile` and the raw eligibility text + structured age/sex for one NCT ID. No matching logic.
- **Create `verdict/trialmatch.py`** — the matching domain. Responsibility: the dataclasses (`PatientProfile`, `Criterion`, `CriterionResult`, `TrialCard`), the deterministic comparators + aggregator, the LLM extraction wrappers, the per-trial `match` orchestration, and the `trial_card` serializer.
- **Create `tests/test_aggregate.py`, `tests/test_structured.py`, `tests/test_trials.py`, `tests/test_trialcard.py`** — unit tests for the deterministic pieces + client (fixture-based).
- **Create `benchmark/trialdeck/*.json`** — the frozen demo deck (pre-verified `trial_card`s) + `benchmark/trialdeck/inputs/*.json` (their source patient notes + NCT IDs) for the golden test.
- **Modify `verdict/webapp.py`** — add `POST /api/match` following the existing `/api/resolve` pattern.
- **Modify `web/src/` (new components + a route/tab)** — ranked-trials view, per-trial ledger, verify-list, plain-LLM foil pane. Reuse existing ledger/badge styling.
- **Reuse (do not rewrite):** `verdict/baseline.py` (`plain_llm_baseline`) for the foil; `verdict/env.py` (`load_dotenv`); the anthropic client pattern in `baseline.py`; the SSE worker pattern in `webapp.py`.

---

## Task 1: Domain models

**Files:**
- Create: `verdict/trialmatch.py`
- Test: `tests/test_trialcard.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trialcard.py
from verdict.trialmatch import PatientProfile, Criterion, CriterionResult, TrialCard

def test_models_construct_with_sensible_defaults():
    p = PatientProfile(age=62, sex="FEMALE", raw_note="62F ...")
    assert p.age == 62 and p.biomarkers == [] and p.labs == {}
    c = Criterion(id="inc1", kind="inclusion", ctype="structured",
                  predicate="Aged 18-75", source_text="Aged 18-75 (inclusive) years old",
                  field="age", op="range", lo=18, hi=75)
    assert c.kind == "inclusion" and c.hi == 75
    r = CriterionResult(id="inc1", kind="inclusion", result="MET", confidence="high",
                        evidence_phrase="62-year-old", note="18<=62<=75",
                        predicate=c.predicate, source_text=c.source_text)
    assert r.result == "MET"
    card = TrialCard(nct_id="NCT06927986", title="t", status="RECRUITING",
                     url="u", verdict="Needs verification", criteria=[r],
                     to_verify=["confirm labs"], n_met=1, n_disqualifying=0, n_to_verify=1)
    assert card.verdict == "Needs verification" and card.criteria[0].id == "inc1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_trialcard.py::test_models_construct_with_sensible_defaults -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'verdict.trialmatch'`

- [ ] **Step 3: Write minimal implementation**

```python
# verdict/trialmatch.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_trialcard.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add verdict/trialmatch.py tests/test_trialcard.py
git commit -m "feat(trialmatch): domain models for patient-trial eligibility"
```

---

## Task 2: The deterministic aggregator (the crown jewel — full truth table)

**Files:**
- Modify: `verdict/trialmatch.py`
- Test: `tests/test_aggregate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_aggregate.py
from verdict.trialmatch import CriterionResult, aggregate

def _r(kind, result):
    return CriterionResult(id="x", kind=kind, result=result, confidence="high",
                           evidence_phrase="", note="", predicate="", source_text="")

def test_exclusion_met_is_ineligible():
    assert aggregate([_r("inclusion", "MET"), _r("exclusion", "MET")]) == "Ineligible"

def test_inclusion_not_met_is_ineligible():
    assert aggregate([_r("inclusion", "NOT_MET"), _r("exclusion", "NOT_MET")]) == "Ineligible"

def test_all_inclusions_met_no_exclusions_fire_is_likely_eligible():
    assert aggregate([_r("inclusion", "MET"), _r("inclusion", "MET"),
                      _r("exclusion", "NOT_MET")]) == "Likely eligible"

def test_any_insufficient_without_definitive_fail_is_needs_verification():
    assert aggregate([_r("inclusion", "MET"), _r("inclusion", "INSUFFICIENT"),
                      _r("exclusion", "NOT_MET")]) == "Needs verification"

def test_exclusion_insufficient_is_needs_verification():
    assert aggregate([_r("inclusion", "MET"), _r("exclusion", "INSUFFICIENT")]) == "Needs verification"

def test_definitive_fail_beats_insufficient():
    # a NOT_MET inclusion is disqualifying even if another criterion is unresolved
    assert aggregate([_r("inclusion", "NOT_MET"), _r("inclusion", "INSUFFICIENT")]) == "Ineligible"

def test_empty_is_needs_verification():
    assert aggregate([]) == "Needs verification"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_aggregate.py -v`
Expected: FAIL — `ImportError: cannot import name 'aggregate'`

- [ ] **Step 3: Write minimal implementation** (append to `verdict/trialmatch.py`)

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_aggregate.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add verdict/trialmatch.py tests/test_aggregate.py
git commit -m "feat(trialmatch): deterministic eligibility aggregator with full truth table"
```

---

## Task 3: Structured comparators (pure, testable)

**Files:**
- Modify: `verdict/trialmatch.py`
- Test: `tests/test_structured.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_structured.py
from verdict.trialmatch import PatientProfile, Criterion, eval_structured

def _crit(field, op, lo=None, hi=None, kind="inclusion"):
    return Criterion(id="c", kind=kind, ctype="structured", predicate="p",
                     source_text="s", field=field, op=op, lo=lo, hi=hi)

def test_age_in_range_is_met():
    p = PatientProfile(age=62, age_src="62-year-old")
    res, phrase, _ = eval_structured(_crit("age", "range", 18, 75), p)
    assert res == "MET" and phrase == "62-year-old"

def test_age_out_of_range_is_not_met():
    p = PatientProfile(age=80, age_src="80yo")
    res, _, _ = eval_structured(_crit("age", "range", 18, 75), p)
    assert res == "NOT_MET"

def test_missing_field_is_insufficient():
    p = PatientProfile()  # no age
    res, phrase, _ = eval_structured(_crit("age", "range", 18, 75), p)
    assert res == "INSUFFICIENT" and phrase == "not stated"

def test_ecog_max_is_met():
    p = PatientProfile(ecog=1, ecog_src="ECOG 1")
    res, _, _ = eval_structured(_crit("ecog", "range", 0, 1), p)
    assert res == "MET"

def test_lab_min_threshold():
    p = PatientProfile(labs={"ANC": 1.8})
    res, _, _ = eval_structured(_crit("ANC", "min", lo=1.5), p)
    assert res == "MET"
    res2, _, _ = eval_structured(_crit("ANC", "min", lo=2.0), p)
    assert res2 == "NOT_MET"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_structured.py -v`
Expected: FAIL — `ImportError: cannot import name 'eval_structured'`

- [ ] **Step 3: Write minimal implementation** (append to `verdict/trialmatch.py`)

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_structured.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add verdict/trialmatch.py tests/test_structured.py
git commit -m "feat(trialmatch): pure structured-criterion comparators"
```

---

## Task 4: ClinicalTrials.gov REST v2 client

**Files:**
- Create: `verdict/trials.py`
- Test: `tests/test_trials.py` + `tests/fixtures/ctgov_search.json`, `tests/fixtures/ctgov_study.json`

**Reference:** CT.gov v2 — search `GET https://clinicaltrials.gov/api/v2/studies?query.cond=<cond>&filter.overallStatus=RECRUITING&pageSize=N&fields=...`; single study `GET https://clinicaltrials.gov/api/v2/studies/<NCT>`. Eligibility lives at `protocolSection.eligibilityModule` (`eligibilityCriteria` text, `minimumAge`, `maximumAge`, `sex`).

- [ ] **Step 1: Save two real fixtures (one-time, using the network)**

Run:
```bash
mkdir -p tests/fixtures
curl -s "https://clinicaltrials.gov/api/v2/studies?query.cond=non-small%20cell%20lung%20cancer&filter.overallStatus=RECRUITING&pageSize=3&fields=NCTId,BriefTitle,OverallStatus" -o tests/fixtures/ctgov_search.json
curl -s "https://clinicaltrials.gov/api/v2/studies/NCT06927986" -o tests/fixtures/ctgov_study.json
```
Expected: both files non-empty JSON. (If NCT06927986 is gone by build time, pick any recruiting NSCLC NCT from the search fixture.)

- [ ] **Step 2: Write the failing test**

```python
# tests/test_trials.py
import json
from verdict import trials

def test_parse_search(monkeypatch):
    raw = json.load(open("tests/fixtures/ctgov_search.json"))
    monkeypatch.setattr(trials, "_get_json", lambda url: raw)
    got = trials.search_candidates_by_condition("non-small cell lung cancer", page_size=3)
    assert len(got) >= 1
    assert got[0].nct_id.startswith("NCT") and got[0].title

def test_parse_eligibility(monkeypatch):
    raw = json.load(open("tests/fixtures/ctgov_study.json"))
    monkeypatch.setattr(trials, "_get_json", lambda url: raw)
    elig = trials.get_eligibility("NCT06927986")
    assert "Inclusion" in elig.text or "inclusion" in elig.text.lower()
    assert elig.nct_id == "NCT06927986"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_trials.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'verdict.trials'`

- [ ] **Step 4: Write minimal implementation**

```python
# verdict/trials.py
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_trials.py -v`
Expected: PASS. (If the field paths differ in the real fixture, adjust `search_candidates_by_condition`'s parsing to match `tests/fixtures/ctgov_search.json` — inspect the fixture.)

- [ ] **Step 6: Commit**

```bash
git add verdict/trials.py tests/test_trials.py tests/fixtures/ctgov_search.json tests/fixtures/ctgov_study.json
git commit -m "feat(trials): ClinicalTrials.gov REST v2 client (fixture-tested)"
```

---

## Task 5: LLM extraction — patient note → PatientProfile, eligibility text → Criterion[]

**Files:**
- Modify: `verdict/trialmatch.py`
- Test: `tests/test_extract_trialmatch.py` (uses a fake client — LLM output is not deterministic, so we test the *wrapper*, not the model)

**Note on testing:** you cannot unit-test the model's judgment deterministically. Test that (a) the wrapper builds the right request and (b) parses a canned tool-use response into the dataclasses. Real quality is validated by running against the fixtures in Task 9.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extract_trialmatch.py
from verdict import trialmatch

def test_profile_from_tool_json():
    payload = {"age": 62, "age_src": "62-year-old woman", "sex": "FEMALE",
               "diagnosis": "metastatic NSCLC", "biomarkers": ["EGFR exon 19 deletion"],
               "prior_therapies": ["osimertinib"], "ecog": 1, "labs": {}, "cns_status": None}
    p = trialmatch.profile_from_json(payload, raw_note="62F ...")
    assert p.age == 62 and p.sex == "FEMALE" and "EGFR exon 19 deletion" in p.biomarkers

def test_criteria_from_tool_json():
    payload = {"criteria": [
        {"id": "inc1", "kind": "inclusion", "ctype": "structured", "predicate": "Aged 18-75",
         "source_text": "Aged 18-75", "field": "age", "op": "range", "lo": 18, "hi": 75},
        {"id": "exc1", "kind": "exclusion", "ctype": "semantic",
         "predicate": "active CNS metastasis", "source_text": "Patients with active CNS metastasis"}]}
    crits = trialmatch.criteria_from_json(payload)
    assert crits[0].field == "age" and crits[1].ctype == "semantic"
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_extract_trialmatch.py -v`
Expected: FAIL — `AttributeError: module 'verdict.trialmatch' has no attribute 'profile_from_json'`

- [ ] **Step 3: Write implementation** (append to `verdict/trialmatch.py`). Pure parsers first, then the LLM callers that use `anthropic` exactly as `verdict/baseline.py` does (same client construction + `VERDICT_MODEL` env).

```python
import os
from anthropic import Anthropic  # already a dependency (see verdict/baseline.py)

def profile_from_json(d: dict, raw_note: str) -> PatientProfile:
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
    out = []
    for c in d.get("criteria", []):
        out.append(Criterion(
            id=c["id"], kind=c["kind"], ctype=c["ctype"], predicate=c["predicate"],
            source_text=c.get("source_text", ""), field=c.get("field", ""),
            op=c.get("op", ""), lo=c.get("lo"), hi=c.get("hi")))
    return out

def _client() -> Anthropic:
    return Anthropic()

def _model() -> str:
    return os.getenv("VERDICT_MODEL") or "claude-sonnet-5"

_PROFILE_TOOL = {"name": "emit_profile", "description": "Structured patient facts.",
    "input_schema": {"type": "object", "properties": {
        "age": {"type": ["integer", "null"]}, "age_src": {"type": "string"},
        "sex": {"type": ["string", "null"], "enum": ["MALE", "FEMALE", None]},
        "diagnosis": {"type": ["string", "null"]}, "stage": {"type": ["string", "null"]},
        "biomarkers": {"type": "array", "items": {"type": "string"}},
        "prior_therapies": {"type": "array", "items": {"type": "string"}},
        "ecog": {"type": ["integer", "null"]}, "ecog_src": {"type": "string"},
        "labs": {"type": "object"}, "comorbidities": {"type": "array", "items": {"type": "string"}},
        "cns_status": {"type": ["string", "null"]}}, "required": ["age", "sex", "diagnosis"]}}

def extract_profile(note: str) -> PatientProfile:
    msg = _client().messages.create(model=_model(), max_tokens=1024,
        tools=[_PROFILE_TOOL], tool_choice={"type": "tool", "name": "emit_profile"},
        messages=[{"role": "user", "content":
            "Extract ONLY facts explicitly stated in this clinical note. For every field, "
            "put the verbatim phrase in the *_src field, or leave the field null if not stated. "
            "Never infer. Note:\n\n" + note}])
    payload = next(b.input for b in msg.content if b.type == "tool_use")
    return profile_from_json(payload, raw_note=note)

_CRITERIA_TOOL = {"name": "emit_criteria", "description": "One entry per eligibility criterion.",
    "input_schema": {"type": "object", "properties": {"criteria": {"type": "array", "items": {
        "type": "object", "properties": {
            "id": {"type": "string"}, "kind": {"enum": ["inclusion", "exclusion"]},
            "ctype": {"enum": ["structured", "semantic"]},
            "predicate": {"type": "string"}, "source_text": {"type": "string"},
            "field": {"type": "string"}, "op": {"enum": ["range", "min", "max", ""]},
            "lo": {"type": ["number", "null"]}, "hi": {"type": ["number", "null"]}},
        "required": ["id", "kind", "ctype", "predicate", "source_text"]}}}, "required": ["criteria"]}}

def extract_criteria(eligibility_text: str) -> list[Criterion]:
    msg = _client().messages.create(model=_model(), max_tokens=3000,
        tools=[_CRITERIA_TOOL], tool_choice={"type": "tool", "name": "emit_criteria"},
        messages=[{"role": "user", "content":
            "Split this trial's eligibility criteria into one entry each. Mark ctype='structured' "
            "ONLY for age, ECOG, sex, or numeric lab thresholds (fill field/op/lo/hi); everything "
            "else is 'semantic'. Preserve source_text verbatim.\n\n" + eligibility_text}])
    payload = next(b.input for b in msg.content if b.type == "tool_use")
    return criteria_from_json(payload)
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_extract_trialmatch.py -v`
Expected: PASS (parsers tested; LLM callers exercised in Task 9).

- [ ] **Step 5: Commit**

```bash
git add verdict/trialmatch.py tests/test_extract_trialmatch.py
git commit -m "feat(trialmatch): LLM extraction of patient profile + trial criteria (tool-use)"
```

---

## Task 6: Semantic matcher + per-trial `match` orchestration

**Files:**
- Modify: `verdict/trialmatch.py`
- Test: `tests/test_match.py` (inject fake extractors/judge — no network)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_match.py
from verdict import trialmatch as tm
from verdict.trialmatch import PatientProfile, Criterion

def test_match_builds_card_and_verify_list(monkeypatch):
    p = PatientProfile(age=62, age_src="62yo", ecog=1, ecog_src="ECOG 1")
    crits = [
        Criterion("inc1", "inclusion", "structured", "Aged 18-75", "Aged 18-75",
                  field="age", op="range", lo=18, hi=75),
        Criterion("inc2", "inclusion", "semantic", "measurable disease per RECIST", "…", ),
        Criterion("exc1", "exclusion", "semantic", "active CNS metastasis", "…"),
    ]
    # semantic judge: measurable-disease -> INSUFFICIENT (not stated); CNS -> INSUFFICIENT
    monkeypatch.setattr(tm, "judge_semantic",
        lambda crit, prof: ("INSUFFICIENT", "not stated", "not stated", "low"))
    card = tm.match(p, "NCT1", "A trial", "RECRUITING", crits)
    assert card.verdict == "Needs verification"
    assert card.n_met == 1  # only the age inclusion
    assert any("measurable" in v.lower() or "cns" in v.lower() for v in card.to_verify)
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_match.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'match'`

- [ ] **Step 3: Write implementation** (append to `verdict/trialmatch.py`)

```python
_SEMANTIC_TOOL = {"name": "judge", "description": "Decide if the patient meets ONE criterion.",
    "input_schema": {"type": "object", "properties": {
        "result": {"enum": ["MET", "NOT_MET", "INSUFFICIENT"]},
        "evidence_phrase": {"type": "string"},  # verbatim note phrase or "not stated"
        "note": {"type": "string"}, "confidence": {"enum": ["high", "medium", "low"]}},
        "required": ["result", "evidence_phrase", "note", "confidence"]}}

def judge_semantic(crit: Criterion, p: PatientProfile) -> tuple[str, str, str, str]:
    """Return (result, evidence_phrase, note, confidence). Bias to INSUFFICIENT."""
    msg = _client().messages.create(model=_model(), max_tokens=512,
        tools=[_SEMANTIC_TOOL], tool_choice={"type": "tool", "name": "judge"},
        messages=[{"role": "user", "content":
            "Decide ONLY from the patient note whether the patient meets this trial criterion. "
            "If the note does not clearly state the needed fact, answer INSUFFICIENT — never guess.\n\n"
            f"CRITERION ({crit.kind}): {crit.predicate}\nSOURCE: {crit.source_text}\n\n"
            f"PATIENT NOTE:\n{p.raw_note}"}])
    d = next(b.input for b in msg.content if b.type == "tool_use")
    return (d["result"], d.get("evidence_phrase", "not stated"), d.get("note", ""),
            d.get("confidence", "low"))

def match(p: PatientProfile, nct_id: str, title: str, status: str,
          crits: list[Criterion]) -> TrialCard:
    results: list[CriterionResult] = []
    for c in crits:
        if c.ctype == "structured":
            res, phrase, note = eval_structured(c, p)
            conf = "high" if res != "INSUFFICIENT" else "low"
        else:
            res, phrase, note, conf = judge_semantic(c, p)
        results.append(CriterionResult(c.id, c.kind, res, conf, phrase, note,
                                       c.predicate, c.source_text))
    verdict = aggregate(results)
    to_verify = [f"Confirm: {r.predicate}" for r in results if r.result == "INSUFFICIENT"]
    n_met = sum(1 for r in results if r.result == "MET")
    n_disq = sum(1 for r in results
                 if (r.kind == "exclusion" and r.result == "MET")
                 or (r.kind == "inclusion" and r.result == "NOT_MET"))
    return TrialCard(nct_id, title, status,
                     f"https://clinicaltrials.gov/study/{nct_id}", verdict, results,
                     to_verify, n_met, n_disq, len(to_verify))
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_match.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add verdict/trialmatch.py tests/test_match.py
git commit -m "feat(trialmatch): semantic judge + per-trial match orchestration"
```

---

## Task 7: Full pipeline `review(note)` + serialization + ranking

**Files:**
- Modify: `verdict/trialmatch.py`
- Test: `tests/test_review.py` (inject fakes for extractors + trials client)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_review.py
from verdict import trialmatch as tm, trials
from verdict.trialmatch import PatientProfile, TrialCard, card_to_dict, rank_cards, CriterionResult

def _card(nct, verdict, nverify):
    return TrialCard(nct, "t", "RECRUITING", "u", verdict, [], ["x"] * nverify, 1, 0, nverify)

def test_rank_orders_eligible_first_then_fewest_open():
    cards = [_card("A", "Ineligible", 0), _card("B", "Needs verification", 3),
             _card("C", "Likely eligible", 0), _card("D", "Needs verification", 1)]
    order = [c.nct_id for c in rank_cards(cards)]
    assert order == ["C", "D", "B", "A"]

def test_card_to_dict_is_json_safe():
    c = _card("NCT1", "Needs verification", 2)
    d = card_to_dict(c)
    import json; json.dumps(d)  # must not raise
    assert d["nct_id"] == "NCT1" and d["n_to_verify"] == 2

def test_review_orchestrates(monkeypatch):
    monkeypatch.setattr(tm, "extract_profile", lambda note: PatientProfile(age=62, raw_note=note))
    monkeypatch.setattr(trials, "search_candidates_by_condition",
        lambda cond, page_size=5, status="RECRUITING": [trials.Candidate("NCT1", "t", "RECRUITING")])
    monkeypatch.setattr(trials, "get_eligibility",
        lambda nct: trials.Eligibility(nct, "Inclusion: Aged 18-75", "18 Years", "75 Years", "ALL"))
    monkeypatch.setattr(tm, "extract_criteria", lambda text: [])
    cards = tm.review("62F metastatic NSCLC ...", condition="non-small cell lung cancer")
    assert isinstance(cards, list) and cards and isinstance(cards[0], TrialCard)
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_review.py -v`
Expected: FAIL — missing `card_to_dict` / `rank_cards` / `review`

- [ ] **Step 3: Write implementation** (append to `verdict/trialmatch.py`)

```python
from dataclasses import asdict
from verdict import trials as _trials

_RANK = {"Likely eligible": 0, "Needs verification": 1, "Ineligible": 2}

def rank_cards(cards: list[TrialCard]) -> list[TrialCard]:
    return sorted(cards, key=lambda c: (_RANK.get(c.verdict, 3), c.n_to_verify))

def card_to_dict(c: TrialCard) -> dict:
    return asdict(c)

def review(note: str, condition: str | None = None, max_trials: int = 5) -> list[TrialCard]:
    """End-to-end: note -> profile -> candidate trials -> per-criterion match -> ranked cards."""
    profile = extract_profile(note)
    cond = condition or profile.diagnosis or ""
    cards: list[TrialCard] = []
    for cand in _trials.search_candidates_by_condition(cond, page_size=max_trials):
        elig = _trials.get_eligibility(cand.nct_id)
        crits = extract_criteria(elig.text)
        cards.append(match(profile, cand.nct_id, cand.title, cand.status, crits))
    return rank_cards(cards)
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_review.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add verdict/trialmatch.py tests/test_review.py
git commit -m "feat(trialmatch): end-to-end review() + ranking + json serialization"
```

---

## Task 8: Frozen demo deck + golden test

**Files:**
- Create: `benchmark/trialdeck/inputs/case1.json` (a patient note + condition + list of NCT IDs), `scripts/build_trialdeck.py`, `benchmark/trialdeck/case1.json` (generated cards), `tests/test_trialdeck.py`

- [ ] **Step 1: Write the builder script** (`scripts/build_trialdeck.py`)

```python
"""Build the frozen demo deck: run review() once per input case, save the ranked cards.
Run manually with a real key: PYTHONPATH=. .venv/bin/python scripts/build_trialdeck.py"""
import json, glob, os
from verdict.env import load_dotenv
from verdict import trialmatch
load_dotenv()
for inp in sorted(glob.glob("benchmark/trialdeck/inputs/*.json")):
    case = json.load(open(inp))
    cards = trialmatch.review(case["note"], condition=case.get("condition"))
    out = os.path.join("benchmark/trialdeck", os.path.basename(inp))
    json.dump({"note": case["note"], "cards": [trialmatch.card_to_dict(c) for c in cards]},
              open(out, "w"), indent=2)
    print("wrote", out, "-", len(cards), "trials")
```

- [ ] **Step 2: Create one input case** (`benchmark/trialdeck/inputs/case1.json`)

```json
{"note": "62-year-old woman with metastatic EGFR exon-19-deletion non-small cell lung cancer, progressed on first-line osimertinib. ECOG 1. No labs or brain imaging reported.",
 "condition": "non-small cell lung cancer"}
```

- [ ] **Step 3: Generate the frozen deck** (uses network + key, one-time)

Run: `PYTHONPATH=. .venv/bin/python scripts/build_trialdeck.py`
Expected: `benchmark/trialdeck/case1.json` written with ≥1 trial, each carrying a verdict + criteria. **Hand-verify** that at least one trial shows the honest "Needs verification" with an INSUFFICIENT criterion (that's the demo beat). If every criterion resolves MET/NOT_MET, edit the note to omit a fact so abstention shows.

- [ ] **Step 4: Write the golden test** (deck loads + shape holds)

```python
# tests/test_trialdeck.py
import json, glob
def test_deck_cards_have_required_shape():
    files = glob.glob("benchmark/trialdeck/case*.json")
    assert files, "no frozen deck built yet"
    for f in files:
        d = json.load(open(f))
        assert d["cards"], f"{f} has no trials"
        for c in d["cards"]:
            assert c["verdict"] in ("Likely eligible", "Ineligible", "Needs verification")
            assert isinstance(c["criteria"], list)
            assert set(("nct_id", "url", "to_verify", "n_to_verify")) <= set(c)
```

- [ ] **Step 5: Run + commit**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_trialdeck.py -v`
Expected: PASS
```bash
git add scripts/build_trialdeck.py benchmark/trialdeck tests/test_trialdeck.py
git commit -m "feat(trialdeck): frozen demo deck builder + golden shape test"
```

---

## Task 9: API endpoint `POST /api/match`

**Files:**
- Modify: `verdict/webapp.py`

**Reference before writing:** open `verdict/webapp.py` and copy the request/response + error-handling shape of the existing `POST /api/resolve` route (CORS scope, `MAX_CLAIM_LEN`-style guard, concurrency semaphore). Match it.

- [ ] **Step 1: Add the route** (follow the existing `/api/resolve` handler style)

```python
# in verdict/webapp.py, near the other routes
from verdict import trialmatch

@app.post("/api/match")
def api_match(body: dict):
    note = (body.get("note") or "").strip()[:4000]
    if len(note) < 10:
        return {"error": "note too short"}
    cards = trialmatch.review(note, condition=body.get("condition"))
    return {"note": note, "cards": [trialmatch.card_to_dict(c) for c in cards]}
```

- [ ] **Step 2: Manual verification** (no unit test — it hits the live network/LLM)

Run:
```bash
PYTHONPATH=. .venv/bin/python -m uvicorn verdict.webapp:app --port 8010 &
sleep 3
curl -s -X POST localhost:8010/api/match -H 'content-type: application/json' \
  -d '{"note":"62F metastatic EGFR exon-19-del NSCLC, progressed on osimertinib, ECOG 1","condition":"non-small cell lung cancer"}' | python3 -m json.tool | head -40
```
Expected: JSON with `cards[]`, each having `verdict` + `criteria` + `to_verify`. Kill the server after.

- [ ] **Step 3: Commit**

```bash
git add verdict/webapp.py
git commit -m "feat(webapp): POST /api/match endpoint for trial eligibility review"
```

---

## Task 10: UI — ranked trials + per-criterion ledger + verify-list + plain-LLM foil

**Files:**
- Modify: `web/src/` — add a `TrialMatch` view + components; add a tab/route alongside the existing Verdict UI. Reuse the existing badge/ledger CSS classes.

**Data contract (from `card_to_dict`):** `{ note, cards: [{ nct_id, title, status, url, verdict, criteria: [{id, kind, result, confidence, evidence_phrase, note, predicate, source_text}], to_verify: string[], n_met, n_disqualifying, n_to_verify }] }`.

- [ ] **Step 1: Add the input + fetch.** A textarea for the patient note + a "Review trials" button that `POST`s to `/api/match` (dev: Vite proxy to `:8010`, same as the existing `/api/resolve`). While loading, show a spinner. On error, fall back to the frozen deck fetched from `/trialdeck/case1.json` (copy `benchmark/trialdeck/*.json` into `web/public/trialdeck/` in the build).

- [ ] **Step 2: Render the ranked list.** One card per trial, ordered as returned. Card header: trial title + a verdict badge — green `Likely eligible`, red `Ineligible`, amber `Needs verification`. Show the counts line: `{n_met} met · {n_disqualifying} disqualifying · {n_to_verify} to verify`.

- [ ] **Step 3: Render the per-criterion ledger.** For each criterion: an icon (✓ MET green / ✗ NOT_MET red / ❔ INSUFFICIENT amber), the `predicate`, and the `evidence_phrase` (or "not stated"). Semantic criteria get a small "model judgment" tag; structured ones show "rule". Clicking a row expands `source_text` + `note`.

- [ ] **Step 4: Render the verify-list** as a checklist under the ledger (the `to_verify` items).

- [ ] **Step 5: The foil pane.** Left/right split on the hero card: LEFT calls the existing plain-LLM baseline (or a one-line `POST` to a tiny `/api/foil` wrapping `verdict.baseline.plain_llm_baseline("Is this patient eligible for <trial>?")`) showing a confident "Yes/No"; RIGHT is the ledger. Caption: "a bare model just answers; this one shows every criterion and abstains when the note can't decide."

- [ ] **Step 6: Verify in the browser.** Start the server + `preview` the web app; paste the case-1 note; confirm the hero trial shows the amber "Needs verification" with INSUFFICIENT criteria and a verify-list, and the foil says "Yes". Screenshot for the video.

- [ ] **Step 7: Commit**

```bash
git add web/
git commit -m "feat(web): trial-match view — ranked trials, per-criterion ledger, verify-list, foil"
```

---

## Task 11: Honesty rails + deliverables

**Files:**
- Modify: `web/src/` (captions), `README.md`, add `SUBMISSION` blurb, `LICENSE`

- [ ] **Step 1: On-screen honesty captions** (from spec §7): "abstains on what the notes can't decide and tells you what to check"; a footer "Research tool — not medical advice; not a substitute for coordinator + PI review"; the "model judgment vs rule" tag on criteria; "live retrieval is best-effort — the frozen deck is the guarantee" on the live lane. Commit.

- [ ] **Step 2: README section** — one paragraph: named user, the decidable-ledger + abstention differentiator, how to run (`uvicorn verdict.webapp:app --port 8010` + the web app), and the honest boundary. Commit.

- [ ] **Step 3: 100–200-word submission summary** + confirm `LICENSE` is MIT. Commit.

- [ ] **Step 4: Record the 3-minute demo** off the frozen deck (bulletproof), then the live lane as the finale. (Manual — not a code step.)

---

## Notes for the executor

- Run the whole suite after each task: `PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`. It must stay green.
- The engine already works; this plan **adds** modules and a view — it does not modify `verdict/gates.py`, `verdict/certainty.py`, or the existing Verdict verdict path.
- Day 1 = Tasks 1–7 (the whole testable core, offline). Day 2 = Tasks 8–10. Day 3 = Task 10 polish + Task 11.
- If `VERDICT_MODEL` is unset, `_model()` defaults to `claude-sonnet-5`; confirm that's a valid id in `.env` or set it. **Rotate the `.env` key before the repo goes public.**
