# Trial-match validation — data provenance

The gold labels here are **not ours**. That is the entire point: the harness scores our verdicts
against relevance judgments made by physicians for a public IR benchmark, so the accuracy number is
external, not self-graded.

## Source

**TREC 2022 Clinical Trials track** (NIST Text REtrieval Conference), organised by UTHealth / NLM.

- Topics (patient case narratives): <https://trec.nist.gov/data/trials/topics2022.xml>
- Relevance judgments (qrels): <https://trec.nist.gov/data/trials/qrels2022.txt>
- Track overview: <https://www.trec-cds.org/2022.html>

Each qrels line is `topic  0  NCTid  label`, where the physician **label** is:

| label | meaning |
|-------|---------|
| 0 | **not relevant** — the patient is not relevant to the trial in any way |
| 1 | **excluded** — the patient has the target condition but an *exclusion* criterion makes them ineligible |
| 2 | **eligible** — the patient meets both inclusion and exclusion criteria |

We use only labels **1 (excluded)** and **2 (eligible)** — the pairs where matching (not retrieval)
is what is being tested.

## How `goldset.json` was sampled

`scripts/build_trial_goldset.py` selects 6 topics (condition diversity) and, per topic, the first
**2 eligible + 2 excluded** trials (candidates sorted by NCT id — deterministic, no RNG) whose
ClinicalTrials.gov record still resolves with substantial eligibility text. Result: **24 pairs,
12 eligible / 12 excluded.** Each record is `{topic_id, note, nct_id, gold}`; the note is the
verbatim TREC topic narrative.

## How it is scored

`scripts/validate_trialmatch.py` runs the real pipeline (`verdict.trialmatch.review_pair`) on each
pair and compares our verdict to the physician label with the selective-prediction metrics in
`verdict/trialval.py`. Verdict → action: `Ineligible` = rule out · `Likely eligible` = keep ·
`Needs verification` = abstain. The headline safety number is the **confident-error rate** — a
definitive call that contradicts the physician (ruling out an eligible trial, or keeping an
excluded one).

## Honest caveats (do not oversell this)

- **Small N (24).** A calibration signal, not a benchmark.
- **Single, non-deterministic run.** The LLM extraction/judging varies run to run; re-running will
  move the numbers. Report it as "on this run," and ideally average a few runs before quoting.
- **TREC notes are physician-written case *narratives*, not live EHR notes** — cleaner and more
  self-contained than real coordinator input, so the number is likely optimistic vs the wild.
- **Patient-trial-level labels**, not per-criterion, so this validates the *verdict*, not each
  ledger row.

## Redistribution note

The 24 topic narratives are reproduced here from the public TREC 2022 track for reproducibility of
this eval. TREC data is distributed by NIST for research use; attribute the track when citing.
Before this repo is made public, confirm TREC's terms are satisfied by attribution — or switch
`goldset.json` to store only `topic_id`/`nct_id` and fetch note text from the TREC file at run time.
