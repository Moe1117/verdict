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
the human trials aren't in. On 32 breakthrough-medicine claims Verdict was confidently
wrong **zero** times versus a plain model's **six**. It isn't just more accurate — it's the
one that structurally won't bluff.

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
cardiometabolic, repurposing), exact 4-state match vs documented clinical/regulatory consensus:

| Method | Accuracy | Confidently wrong |
|---|---|---|
| **Verdict** (gate engine) | **91%** | **0** |
| Naive study-count vote | 84% | 0 |
| Plain LLM (confident) | 63% | 6 |

Verdict abstains on 12% rather than guess. Its three misses are all conservative — it held
"insufficient" or "contested" where guidelines are more assertive (ezetimibe,
checkpoint-inhibitor pancreatic cancer, psilocybin durability) — never a confidently-wrong
positive. Full per-claim results are in the repo.

## What's next

Wire the live extract/retrieve path into the UI (today the demo replays the verified
frozen corpora); widen coverage; calibrate the sufficiency gate on the handful of claims
where clinical consensus is more assertive than the current evidence tier.
