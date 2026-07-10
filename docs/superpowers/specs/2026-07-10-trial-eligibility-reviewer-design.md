# Trial Eligibility Reviewer ("TrialLedger", working name) — Design Spec

**Date:** 2026-07-10
**Context:** "Built with Claude: Life Sciences" hackathon, Builder track, solo, ~3 days. Reuses the Verdict decidable-decision engine + UI. On-brief with the judges' own "clinical-trial matcher" example.

---

## 1. Motivation & named user

**User:** a clinical research coordinator (or a trial-navigating oncologist) who has one patient and needs to know which *recruiting* trials the patient actually qualifies for — and be able to *defend every match* to a PI or a monitor.

**Pain:** matching a patient to trials is hours of manual chart-vs-criteria checking; existing AI matchers are black boxes that return a ranked "match" and can silently assert eligibility a criterion doesn't support. A false "eligible" burns a screening slot and raises false hope; a false "ineligible" denies a patient a trial.

**Our counter-position (the whole pitch):** *Every other matcher says "match." This one shows the decidable reasoning for every criterion — and it will never call a patient eligible when a criterion is unmet or unknown. It abstains and hands the coordinator the exact list to verify.* "Never confidently wrong" finally lands where it is clinically load-bearing.

This is deliberately counter-positioned against an ML-heavy field: they win on model performance, we win on **deterministic, auditable, calibrated-abstaining decisions** — the axis Anthropic + Gladstone judges reward (honesty, interpretability), and one a 3-day ML build cannot match.

---

## 2. What it does (the decision)

Input: a free-text patient note. Output: a ranked list of candidate recruiting trials, each with:
- an **eligibility verdict** — `Likely eligible` / `Ineligible` / `Needs verification` (never a bare "match"),
- a **per-criterion audit ledger** — each inclusion/exclusion criterion → `MET` / `NOT MET` / `INSUFFICIENT DATA`, tied to the exact phrase in the note (or "not stated"),
- a **to-verify worklist** — the specific criteria the note cannot decide, phrased as actions ("confirm brain MRI shows no active CNS mets"),
- a per-trial confidence that is **honest about which criteria are structured (high) vs semantic (graded)**.

---

## 3. Non-goals (YAGNI)

- NOT a replacement for coordinator/PI judgment; it triages and shows its work.
- NOT solving genomic-marker parsing beyond what Claude can read from the note text.
- NOT a full EHR integration; input is a pasted note (or a seeded vignette).
- NOT claiming the Verdict *conformal guarantee* transfers to this task (different task, no fit set) — see §7.
- NOT geographic/logistics matching (site distance, insurance) in v1 — trials are filtered to `RECRUITING` and shown with their listed locations only.

---

## 4. Architecture & components

Same discipline as Verdict: **Claude extracts structured data; deterministic code makes and aggregates the calls; the system abstains when it cannot decide.** New matching logic, reused rendering + ethos.

1. **`verdict/trials.py` (new)** — a thin ClinicalTrials.gov **REST API v2** client (`https://clinicaltrials.gov/api/v2/studies`). The `c-trials` MCP is for *authoring/validation only*; the deployed app calls the public API directly. Functions: `search_candidates(profile, page_size)` → candidate studies (filtered `status=RECRUITING`); `get_eligibility(nct_id)` → the raw inclusion/exclusion text + structured `minimumAge/maximumAge/sex`. One clear interface; independently testable against recorded fixtures.

2. **Patient-note extraction (new, LLM)** — Claude reads the free-text note → a structured `PatientProfile` (age, sex, diagnosis + stage, biomarkers/mutations, prior therapy lines, ECOG, key labs, comorbidities, CNS status), each field carrying the **verbatim source phrase** or `null` if not stated. LLM-as-extractor only.

3. **Criteria extraction (new, LLM)** — Claude reads a trial's eligibility text → an ordered list of `Criterion` objects: `{ id, kind: inclusion|exclusion, type: structured|semantic, predicate, source_text }`. `structured` = machine-comparable (age range, ECOG range, sex, lab thresholds, prior-line counts, measurable-disease-present). `semantic` = requires domain judgment (mutation class, histology subtype, "active" disease states).

4. **The matcher (new, the core)** — for each `Criterion` vs the `PatientProfile`:
   - **structured** → LLM-extracted values + **deterministic comparison** (`18 ≤ 62 ≤ 75` → MET). If the needed patient field is `null` → **INSUFFICIENT DATA**.
   - **semantic** → a single Claude judgment returning `MET/NOT_MET/INSUFFICIENT` **plus** a self-reported confidence and the reason; **defaults to INSUFFICIENT** whenever the note does not clearly support a decision (bias to abstain, never guess).
   - Output per criterion: `{ id, result, confidence, evidence_phrase | "not stated", note }`.

5. **Aggregation (new, deterministic — the "no LLM in the verdict" part)** — a pure function over the per-criterion results:
   - any **exclusion `MET`** OR any **inclusion `NOT MET`** → `Ineligible` (a definitive fail on either side);
   - all **inclusions `MET`** and all **exclusions `NOT MET`** (nothing `INSUFFICIENT`) → `Likely eligible`;
   - otherwise (something `INSUFFICIENT` on either side, nothing definitively failing) → `Needs verification`.
   This rule is fixed, inspectable, and shown. Ranking: `Likely eligible` > `Needs verification` (fewest open items first) > `Ineligible`.

6. **Serialization (new, mirrors `verdict/cards.py`)** — a `trial_card` payload: verdict, ranked criteria ledger, verify-list, confidence, trial metadata + CT.gov URL. One serializer so frozen deck and live lane cannot drift.

7. **UI (reuse + extend `web/`)** — reuse the existing ledger + certainty rendering. New views: a patient-note input; a ranked trial list; per-trial the criterion ledger (MET green / NOT-MET red / INSUFFICIENT amber, each with its evidence phrase) + the verify-list; the plain-LLM foil pane ("a bare model just says eligible").

8. **`verdict/webapp.py` (extend)** — add `POST /api/match` (sync) and an SSE progress stream reusing the existing worker-thread pattern; serve the extended `web/dist`.

---

## 5. Data flow

`patient note` → (LLM) `PatientProfile` → `trials.search_candidates` → for each candidate: `trials.get_eligibility` → (LLM) `Criterion[]` → `matcher` per criterion → `aggregate` → `trial_card` → rank → UI. Frozen-deck path bypasses the network and serves pre-built `trial_card` JSON.

---

## 6. The demo

**Money-shot:** paste a real oncology vignette (e.g. "62F, metastatic EGFR exon-19-del NSCLC, progressed on osimertinib, ECOG 1"). Candidate trials render with per-criterion ledgers. The hero trial shows *"4 criteria MET, 0 disqualifying, 8 to verify — I won't call this eligible until you confirm the brain MRI and recent labs,"* directly beside a plain-LLM foil confidently answering *"Yes, eligible."* Then click a criterion → the exact note phrase + how the call was made.

**Bulletproofing:** a **frozen deck** of ~3 pre-verified patient×trial-set cases (real NCT IDs, criteria and matches verified by hand on Day 1) drives the recorded demo with zero network. A **best-effort live lane** ("paste your own note") runs the full pipeline, captioned as non-deterministic on retrieval.

---

## 7. Honesty rails & the deterministic/semantic boundary (critical — do not overclaim)

- **What is deterministic:** the *aggregation* (per-criterion results → verdict) and *structured-criterion comparisons*. These are shown and reproducible.
- **What is LLM judgment:** *semantic-criterion* evaluation (e.g. "is exon-19-del an EGFR-sensitizing mutation?"). We label these on-screen as model judgments with a confidence, and they **bias to INSUFFICIENT** rather than guess. We do NOT pitch the whole tool as "no LLM in the decision" — only the aggregation and structured comparisons.
- **Abstention is the feature:** any criterion the note cannot support → `INSUFFICIENT DATA` + a verify action. The verdict is never `Likely eligible` while any inclusion is unresolved.
- **No conformal claim:** the Verdict conformal guarantee is *not* asserted here (different task, no calibration set). Confidence is per-criterion and honest, not guaranteed.
- **Investigator-discretion criteria** ("investigator deems suitable") → flagged as human-judgment, never faked.
- **Live retrieval is best-effort;** the frozen deck is the guarantee.
- **Not medical advice / not a substitute for coordinator + PI review** — stated on screen.

---

## 8. Reuse vs build

**Reuse:** the ledger + certainty UI components and styling; the LLM-extraction pattern (`extract.py` style); the `webapp.py` sync+SSE scaffolding; `env.py`; the frozen-deck-plus-live-lane demo pattern; the plain-LLM foil (`baseline.py`).
**Build new:** `trials.py` (CT.gov v2 client), patient-note + criteria extraction prompts/schemas, the matcher, the deterministic aggregator, the `trial_card` serializer, and the ranked-trials + verify-list UI.

---

## 9. Milestones (3 days)

- **Day 1 — matching core, verified offline.** `PatientProfile` + `Criterion` extraction schemas; the matcher (structured deterministic + semantic-graded-abstaining); the deterministic aggregator with unit tests; hand-verify ~3 patient×trial cases and freeze their `trial_card` JSON. No UI, no live network yet.
- **Day 2 — retrieval + UI.** `trials.py` against CT.gov v2 (with recorded fixtures for tests); ranked-trials view + per-criterion ledger + verify-list rendering; wire the frozen deck end-to-end in the browser.
- **Day 3 — live lane + polish + deliverables.** `POST /api/match` + SSE; best-effort live "paste your own note"; the plain-LLM foil pane; all honesty captions (§7); a small calibration/how-it-decides panel; record the 3-min video; 100–200-word summary; MIT license; rehearse frame timing.

---

## 10. Testing

- Unit: the aggregator (truth table over MET/NOT-MET/INSUFFICIENT × inclusion/exclusion); structured comparators (age/ECOG/labs).
- Fixture: `trials.py` against recorded CT.gov responses (offline, deterministic).
- Golden: the 3 frozen `trial_card`s regenerate byte-identical from committed inputs (frozen deck cannot silently drift).
- Extraction spot-checks: a handful of note→profile and eligibility→criteria pairs asserted by hand.

---

## 11. Risks

- **In-field crowding** (other trial-matcher entries): mitigated by the rigor angle — decidable per-criterion ledger + calibrated abstention + "never falsely eligible," which black-box matchers do not offer. The demo must lead with that, not with "we match trials."
- **Semantic-criterion errors** (wrong MET on a judgment call): mitigated by abstain-by-default + labeling semantic calls as model judgments + a confidence.
- **Demo craft:** the ledger + foil timing must be clean; frozen deck removes network risk.
- **Scope creep:** no EHR, no logistics, no genomics parsing beyond note text (see §3).
