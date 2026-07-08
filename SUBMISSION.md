# Verdict — hackathon submission

**Built with Claude: Life Sciences · Builder track · July 7–13 2026**
Repo: https://github.com/Moe1117/verdict · Demo video: _(link)_

---

## Summary (≈165 words — the submission blurb)

Verdict is a decidable evidence resolver for biomedical claims. Paste a claim —
*"ivermectin improves clinical outcomes in COVID-19"* — and it returns one of four
states: **Supported, Not Supported, Contested,** or **Insufficient**, with a calibrated
confidence and an audit ledger that traces every study to the gate it fed. When the
evidence can't decide, it abstains instead of guessing.

The architecture is the point. Claude does one job: structured extraction from each
study — design, sample size, effect, direction, risk of bias. A **deterministic gate
engine, with no LLM in the verdict path,** makes the call. So every verdict is a pure,
auditable function of the evidence. Known-bad studies — retracted, fabricated — are
excluded *before* the gate, so a fraud-driven result a plain model would happily repeat
never reaches the answer. On a blind set of 31 claims, Verdict was confidently wrong
**zero** times, versus a plain model's **two**. It isn't always more accurate — it's the
one that structurally won't bluff.

---

## What it does

Grades the *state of published evidence* for a biomedical efficacy or drug-repurposing
claim, and shows its work. Four evidence states plus a measured reject option (abstain).
Every verdict comes with a gate trace and an evidence ledger — click any verdict, see the
studies, the retractions, and the exact gate each one passed or failed.

It is a research and literature-triage tool for professionals. **Not** medical advice, a
diagnosis, or a treatment recommendation.

## Who it's for

A translational researcher, medical-affairs reviewer, or early-stage biotech scientist
triaging a hypothesis — *"is this worth six months?"* — who needs a sourced, honest read,
including an explicit "the evidence isn't there yet."

## How we built it (with Claude)

- **Claude = structured extraction only.** From each study it pulls design, N, effect
  direction, population fit, and integrity flags into typed rows. It never decides.
- **Deterministic gate engine decides.** A pure function over the extracted rows: an
  integrity screen (drops retracted/fabricated work), a direct-evidence gate, a
  sufficiency gate (this is where it abstains), and consistency/definitive-evidence gates.
- **Calibration layer** maps gate configurations to an empirically-grounded confidence —
  selective prediction with a reject option, not a vibe.
- **Live retrieval** from PubMed (NCBI E-utilities) and ClinicalTrials.gov; the demo runs
  off frozen, in-window verified corpora so it can't fail live.
- Web UI contrasts a plain LLM's confident answer against Verdict's audited call.

## The honest scorecard

Blind cold set, 31 claims, exact 4-state match vs an independent expert-consensus gold:

| Method | Accuracy | Confidently wrong |
|---|---|---|
| **Verdict** (gate engine) | **81%** | **0** |
| Naive study-count vote | 77% | 0 |
| Plain LLM (confident) | 74% | 2 |

Where it loses: on emerging pipeline drugs with thin literature, Verdict is conservative
to a fault (62% vs a plain model's 75%). It trades raw accuracy for never being
confidently wrong, and for abstaining when the evidence can't decide. Full evals —
including the set where Verdict underperforms — are in the repo.

## What's next

Wire the live extract/retrieve path into the UI (today the demo replays verified frozen
corpora); calibrate the sufficiency gate to close the over-decide gap on borderline
Contested/Insufficient claims; widen coverage beyond the demo deck.
