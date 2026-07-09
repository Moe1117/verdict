# Verdict — hackathon submission

**Built with Claude: Life Sciences · Builder track · July 7–13 2026**
Repo: https://github.com/Moe1117/verdict · Demo video: _(link)_

---

## Summary (≈170 words — the submission blurb)

Verdict is a decidable evidence resolver for biomedical claims. Paste a claim —
*"aducanumab improves cognitive outcomes in Alzheimer's"* — and it returns one of four
states: **Supported, Not Supported, Contested,** or **Insufficient**, with a confidence
and an audit ledger tracing every study to the gate it fed. When the evidence can't
decide, it abstains instead of guessing.

The architecture is the point. Claude does one job: structured extraction from each
trial — design, sample size, effect, and whether the endpoint is the *real* outcome or a
**surrogate**. A **deterministic gate engine, with no LLM in the verdict path,** makes the
call. So every verdict is a pure, auditable function of the evidence: it sets aside
aducanumab's amyloid-PET surrogate and returns Contested; it scores bevacizumab on
survival (not PFS) and returns Not Supported; it abstains on metformin-for-aging because
the human trials aren't in. On 32 breakthrough-medicine claims the **gate engine** is
confidently wrong **zero** times versus a plain model's **six**. Run end-to-end from raw
claims — Claude extracting live — the full **product** scores 66% with **three** confident
false-positives: still far fewer than the model's six, and it abstains rather than bluff.
We report both numbers.

---

## What it does

Grades the *state of published evidence* for a drug-efficacy or repurposing claim, and
shows its work. Four evidence states plus a measured reject option (abstain). Click any
verdict to see the trials, the surrogate-vs-outcome flags, the retractions, and the exact
gate each study passed. A research / literature-triage tool for clinicians and reviewers —
**not** medical advice, a diagnosis, or a treatment recommendation.

## Who it's for

A clinician, medical-affairs reviewer, or translational scientist triaging a
drug-efficacy or repurposing question — *"is this real, or is it hype and a surrogate?"* —
who needs a sourced, honest read, including an explicit "the evidence isn't there yet."

## How we built it (with Claude)

- **Claude = structured extraction only.** From each trial it pulls design, N, effect
  direction, population fit, and — decisively — whether the endpoint measures the *claimed*
  outcome or only a surrogate (amyloid vs cognition, PFS vs OS, LDL vs CV events). It never
  decides.
- **Deterministic gate engine decides.** A pure function over the rows: integrity screen
  (drops retracted/withdrawn work), outcome-directness (surrogate-only → Insufficient), a
  sufficiency gate (abstains on thin evidence), and a definitive tier where a *supermajority*
  of large RCTs decides while a genuine split (aducanumab's EMERGE vs ENGAGE) stays Contested.
- **Live retrieval** from PubMed (NCBI E-utilities) and ClinicalTrials.gov. The 32-claim
  clinical benchmark was built and adversarially fact-checked from those sources.
- Web UI contrasts a plain LLM's confident answer against Verdict's audited call.

## The honest scorecard

Blind clinical benchmark, 32 breakthrough-medicine claims (GLP-1, anti-amyloid, oncology,
cardiometabolic, repurposing), exact 4-state match vs documented clinical/regulatory consensus.
We report **two** numbers — the gate engine in isolation, and the full live product — because
they measure different things:

| Method | Accuracy | Confident false-positives |
|---|---|---|
| **Verdict — gate engine** (over verified evidence rows) | **91%** | **0** |
| Naive study-count vote | 84% | 0 |
| Plain LLM (confident yes/no) | 63% | 6 |
| **Verdict — full live product** (Claude extracts from raw PubMed / ClinicalTrials.gov) | **66%** | **3** |

The **gate engine** — the deterministic logic, holding extraction fixed — is confidently wrong
zero times. The **live product** — Claude parsing the claim, retrieving, and extracting each
abstract end-to-end — scores 66% with **three** confident false-positives (asserting *Supported*
where the truth is negative or genuinely contested), still far fewer than a plain LLM's six, and
it abstains on 16% rather than guess. The ~25-point gap is honest: it is retrieval recall +
extraction error, not gate logic (`scripts/live_benchmark.py` measures it; per-claim results in
`web/public/live_eval.json`). We lead with both, because hiding the live number would be exactly
the bluffing this tool exists to prevent.

We also measured **Claude's extraction in isolation** (studies held fixed, retrieval removed;
`scripts/extraction_eval.py`, 162 studies): it matches the gold rows **100%** on integrity, 93%
on design, 90% on effect-direction polarity, and 85% on the surrogate-vs-outcome flag — and its
errors are **conservative** (a positive trial read as null, more endpoints flagged as surrogate),
which push toward abstention, not false positives. So the extraction is sound and errs in the
cautious direction; the remaining live gap is dominated by retrieval recall.

**Calibration is measured, and honestly imperfect.** Certainty is an ordinal grade (High /
Moderate / Low / Very Low) with empirically-measured reliability: High is right **~82%
out-of-sample** (95% CI 78–93%), ECE 0.16 on 82 held-out claims. A distribution-free conformal
guarantee bounds committed error **≤20% at High** (held in 93% of random exchangeable splits) —
and we state openly it does **not** hold under the deliberate covariate shift to the held-out
set. Calibration and the guarantee are measured on the **gate engine over verified rows**; the
live product is measured separately (66%) and is not yet re-calibrated end-to-end.

## What's next

The measured live gap is dominated by **retrieval recall** — several misses rest on a pivotal
trial the query didn't surface (e.g. a failed confirmatory RCT). Next: an isolated extraction
eval to separate retrieval error from extraction error, stronger retrieval (pubtype-filtered +
trial-registry recall), an end-to-end re-calibration on the live pipeline, and wiring the live
path into the UI so the demo resolves a fresh claim on camera (today it replays the verified
frozen corpora).
