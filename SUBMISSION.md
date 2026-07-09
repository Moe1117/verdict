# Verdict — hackathon submission

**Built with Claude: Life Sciences · Builder track · July 7–13 2026**
Repo: https://github.com/Moe1117/verdict · Demo video: _(link)_

---

## Summary (≈170 words — the submission blurb)

Verdict is a decidable evidence resolver for biomedical claims. Paste one —
*"aducanumab improves cognitive outcomes in Alzheimer's"* — and it resolves live,
streaming each study in as Claude extracts it, then returns one of four states:
**Supported, Not Supported, Contested,** or **Insufficient**, with a confidence and an audit
ledger tracing every study to the gate it fed. When the evidence cannot decide it abstains
rather than return an unsupported verdict — and states what evidence would change its mind.

The architecture is the point. Claude does one job: structured extraction from each
trial — design, sample size, effect, and whether the endpoint is the *real* outcome or a
**surrogate**. A **deterministic gate engine, with no LLM in the verdict path,** issues the
verdict. So every verdict is a pure, auditable function of the evidence: it sets aside
aducanumab's amyloid-PET surrogate and returns Contested, and abstains on metformin-for-aging
because the human trials aren't in yet. The **gate engine** is 91% accurate here; the full live
**product** scores 62% and abstains on 19% rather than overstate — both reported. We don't claim
to out-score a strong LLM on famous claims (a naive Claude gets 78%). Verdict's edge is that it
*shows its work*, is calibrated, abstains when the evidence is genuinely split, and won't
reproduce a fraud-driven result.

---

## What it does

Grades the *state of published evidence* for a drug-efficacy or repurposing claim, and
shows its work. Four evidence states plus a measured reject option (abstain). Click any
verdict to see the trials, the surrogate-vs-outcome flags, the retractions, and the exact
gate each study passed. Paste your own claim and it resolves live — retrieving, extracting,
and gating end-to-end; when it abstains, it names the evidence that would make the claim
decidable. A research / literature-triage tool for clinicians and reviewers — **not** medical
advice, a diagnosis, or a treatment recommendation.

## Who it's for

A clinician, medical-affairs reviewer, or translational scientist triaging a
drug-efficacy or repurposing question — *"is this real, or is it hype and a surrogate?"* —
who needs a sourced, rigorous assessment, including an explicit determination that the evidence is not yet sufficient.

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
- **Live lane — paste your own claim.** Verdict resolves it end-to-end in the browser:
  Claude parses it, PubMed and ClinicalTrials.gov are searched, each study is extracted and
  streams in as it lands, then the deterministic gate issues the verdict — over Server-Sent
  Events, so you watch the pipeline work. The verified frozen deck stays as a fallback, so a
  demo can't be broken by the network.
- **Research directive.** Every verdict states what would change it — for an abstention, the
  specific evidence that would make the claim decidable (the missing trial, the non-surrogate
  outcome); for a decided verdict, the result that would overturn it. Deterministic, read from
  the gate outcome.
- **Falsification pass.** Before committing a decided verdict, the live pipeline runs a second,
  *disconfirming* retrieval — it actively searches for the evidence that would overturn itself,
  then lets the gate re-decide over the union. A verdict that survives has survived an attempt to
  refute it; a missed contradicting trial gets its chance to flip it. Measured on the live benchmark,
  the pass flips solanezumab off a confident *Supported*, taking the strict confident false-positive
  **1→0** and the broad count **3→1**, at a ~4-point accuracy cost (66%→62%) and +3 points abstention
  — the honest safety trade.
- **Adversarial hardening.** We red-teamed the engine with 40 cases grounded in real trials, built
  to force a confident error. The gate held on 36; of the breaks, two were genuine bugs (a large
  *null* meta-analysis and a lone pooled meta were each letting a positive signal through) — both
  fixed and independently verified, with **zero regression** across the curated, cold, and
  held-out benchmarks.
- Web UI contrasts a plain LLM's confident answer against Verdict's audited call.

## The honest scorecard

Blind clinical benchmark, 32 breakthrough-medicine claims (GLP-1, anti-amyloid, oncology,
cardiometabolic, repurposing), exact 4-state match vs documented clinical/regulatory consensus.
Every **plain-LLM** answer is a **real, logged Claude call** (`scripts/live_baseline.py`, committed
to `benchmark/baselines_audit.json`) — a reproducible tool-vs-tool comparison, not a cached string.

| Method | Accuracy | Confident false-positives |
|---|---|---|
| **Verdict — gate engine** (logic only, over verified rows) | **91%** | **0** |
| Naive study-count vote | 84% | 0 |
| Plain LLM — naive Claude (confident yes/no, no tools) | 78% | 0 · 3 † |
| **Verdict — full live product** (Claude extracts end-to-end, falsification pass on) | **62%** | 0 strict · 1 broad † |

† Strict definition (a confident *Supported* where the truth is Not-Supported/Insufficient): **every
method here is 0** — a strong naive Claude already rejects the debunked claims (ivermectin, HCQ,
solanezumab). Broad definition (a confident *Supported* on a claim whose evidence is genuinely
**Contested**): naive Claude commits **3** (it cannot say "contested"); Verdict returns **Contested**
on those.

**We are deliberately not claiming to beat a plain LLM.** On famous, well-documented claims a strong
naive Claude is a hard baseline — 78%, and it confidently rejects the frauds — because it has read
the very literature the benchmark is drawn from. The live product's **62% is *below* naive Claude's
78%** on this set, and that is honest: for claims a model has effectively memorized, retrieval +
extraction only add noise. So an all-famous-claims benchmark *understates* where the architecture
earns its keep. Verdict's real edge is threefold: (1) it is **sourced and auditable** — every verdict
traces to trials + gates, where the LLM gives an unsourced sentence; (2) it is **calibrated and
abstains** — it returns Contested/Insufficient on the borderline claims where naive Claude commits a
confident wrong answer; (3) it **resists a fraud-driven result** — retracted evidence is excluded
before the gate. Where the architecture should most clearly win — **novel claims a model has not
memorized** — we test with a dedicated novel-claim benchmark (see *Novel claims* below). The 91%→62%
gap is retrieval recall + extraction error, honestly reported (`scripts/live_benchmark.py`).

**The gold set is externally valid — not just circular.** The 91% measures whether the gate
reproduces the author-written gold over structured rows; on its own that is auditability, not
external accuracy (the author wrote the rows, the gold, *and* the gate). So we independently
cross-checked a representative **12 gold labels** — spanning Supported / Not-Supported / Contested /
Insufficient — against external landmark evidence (NEJM/Lancet/JCO RCTs, meta-analyses, FDA and
guideline actions), adjudicating from the sources *before* comparing to the gold
(`benchmark/gold_external_audit.json`). External evidence agreed **12/12** — including the two claims
the live pipeline itself mis-called (osimertinib and trastuzumab: the gold is right, the pipeline
*under*-called them) and the ivermectin case, where the raw literature only looks mixed because a
pooled meta-analysis is contaminated by the retracted Elgazzar trial and only the quality-weighted
verdict is Not-Supported. The 91% is auditability over an externally-validated gold, not a
self-graded exam.

We also measured **Claude's extraction in isolation** (studies held fixed, retrieval removed;
`scripts/extraction_eval.py`, 162 studies): per field it matches the gold rows **100%** on integrity,
93% on design, 91% on effect-direction polarity, and 85% on the surrogate-vs-outcome flag — but it
gets **every field of a study exactly right only 62% of the time** (raw effect-direction 82%), which
is the load-bearing number since one wrong field can flip a gate. Its errors are **conservative** (a
positive trial read as null, more endpoints flagged as surrogate), which push toward abstention, not
false positives — so the remaining live gap is dominated by retrieval recall, but extraction is the
next-largest lever.

**Calibration is measured, and measurably imperfect.** Certainty is an ordinal grade (High /
Moderate / Low / Very Low). The honest out-of-sample check is a calibration fit on the **dev set
only**, then tested on held-out claims never used to fit it. High-certainty is right **79% on the
original held-out (n=24 High; heldout + heldout_v2)** and **82% across all held-out (n=50 High)** —
a later 40-claim set was added to tighten the interval, so we report *both* rather than only the
larger number, and note the pooled dev+held-out buckets (87%, 95% CI 78–93%, n=71) include the fit
data and are **not** out-of-sample. ECE 0.156 across 82 held-out claims. A distribution-free
conformal guarantee bounds committed error **≤20% at High** (held in 93% of random exchangeable
splits) — and it does **not** hold under the deliberate covariate shift to the held-out set (27%
realized error), which we state openly. Calibration and the guarantee are measured on the **gate
engine over verified rows**; the live product (62%) is not yet re-calibrated end-to-end.

## Novel claims — where the architecture is supposed to win

The curated benchmark is all famous claims a strong LLM has read. To probe the opposite — claims a
Jan-2026-cutoff model has *not* pinned down — we had agents search live PubMed for recent (2024–2025)
trial readouts, ground each in a real paper, and independently verify it (`scripts/novel_benchmark.py`,
`benchmark/novel_claims.json`). This is a small **n=3 probe** — the verification fan-out was rate-
limited — so it illustrates rather than proves; the harness + verified claim set are committed and
reusable to scale it up.

| | naive Claude | Verdict (live) |
|---|---|---|
| Accuracy | 67% (2/3) | 67% (2/3) |
| Confident false-positives | **1** | **0** |
| Abstains | never | 33% |

Same accuracy — but on the one claim the model hadn't pinned down (navacaprant, a kappa-opioid-
antagonist antidepressant that **missed** its primary endpoint), naive Claude confidently asserted it
**works**; Verdict retrieved the evidence, found it insufficient for a confident call, and
**abstained**. That is the never-confidently-wrong property showing exactly where a model fails: it
hallucinates a confident yes on a recent result it doesn't know, and Verdict doesn't. (Claude knew the
other two 2024 results correctly — the novelty only bit on one, which we report honestly.)

## What's next

The live path is now wired into the UI — paste a claim and Verdict resolves it end-to-end on
camera, streaming each study in as it is extracted, so the tool works on anything, not just the
curated deck. The remaining gap is **retrieval recall**: several live misses rest on a pivotal
trial the query didn't surface (e.g. a failed confirmatory RCT). Next: stronger retrieval
(pubtype-filtered PubMed + trial-registry recall) and an end-to-end re-calibration of the live
pipeline — certainty is currently calibrated on the gate engine over verified rows, not yet on
the full live product.
