# Verdict — 3-minute demo script (clinical)

**Target:** ≤ 3:00. Screen recording of the web app + voiceover.
**Setup:** run **both** servers — the API (`uvicorn verdict.webapp:app --port 8010`) and the
UI (`npm --prefix web run dev`, `:5175`) — and full-screen the browser at ~1280px. Every
curated claim deep-links by URL hash — jump straight to a tab: `/#M06`, `/#M07`, `/#M09`,
`/#M12`, `/#M24`, `/#M01`, `/#C08`. The scorecard is at the bottom of the page.
**Live beat (scene 7):** the paste-a-claim input resolves a fresh claim end-to-end (~40s of
real retrieval). **Pre-record this** — the live pipeline is non-deterministic run-to-run, so
rehearse your exact claim and cut the ~40s wait down to the streaming highlights in the edit.
A reliable default: *"atorvastatin lowers LDL cholesterol in adults"* → Supported.

Narration is written to be read aloud, first person. Trim a sentence anywhere you run long.

---

### 1 · The problem — 0:00–0:20
**Screen:** App open on `/#M06` (aducanumab). Left "A plain LLM" panel: the confident answer + red ⚠.

> "Ask a language model whether aducanumab helps in Alzheimer's, and you get this — confident,
> fluent: 'yes, it slowed decline 22% and clears amyloid.' But the FDA approved it on the
> amyloid *surrogate*, its two identical phase-3 trials flatly disagreed, and the confirmatory
> trial was abandoned. Verdict is a second opinion built so it can't paper over that."

### 2 · What it is, and Claude's job — 0:20–0:40
**Screen:** Pan to the Verdict panel — the **Contested** badge, then "gate trace — deterministic, no LLM."

> "Claude does one job here: it reads each trial and extracts the structured facts — design,
> sample size, effect, and crucially, whether the endpoint is the *real* outcome or a surrogate.
> It never makes the call. A deterministic gate engine does. So every verdict is an auditable
> function of the evidence — and here it sets the amyloid-PET row aside as a surrogate, sees
> EMERGE positive and its twin ENGAGE negative, and returns Contested."

### 3 · Three verdicts on one drug class — 0:40–1:08
**Screen:** Click through the Alzheimer's trio: `/#M06` aducanumab (Contested), `/#M07`
lecanemab (Supported), `/#M09` solanezumab (Not Supported).

> "Here's what honesty looks like across one drug class. Aducanumab — the trials conflict —
> Contested. Lecanemab — CLARITY-AD met its clinical endpoint cleanly — Supported. Solanezumab —
> failed every pivotal trial — Not Supported. And notice: on solanezumab the plain model actually
> gets it right, and Verdict *agrees* — it isn't a contrarian, it's a calibrated one. Same class,
> three different honest answers, each traceable to the trials."

### 4 · The surrogate trap — 1:08–1:30
**Screen:** Click `/#M12` (bevacizumab). The ledger shows PFS-positive rows set aside; OS rows drive Not Supported.

> "This is the pattern that fools everyone. Bevacizumab for metastatic breast cancer improved
> progression-free survival — a surrogate — so it was approved. It never improved overall
> survival, and the FDA revoked the indication in 2011. A model repeats the approval. Verdict
> scores the claimed outcome — survival — sets the surrogate aside, and returns Not Supported."

### 5 · Knowing when to abstain — and what would change it — 1:30–1:56
**Screen:** Click `/#M24` (metformin for aging). Verdict = **Insufficient**; point to the blue
*"what would make this decidable"* callout beneath the claim.

> "The hardest skill is saying 'I don't know.' Does metformin slow aging? There's a famous
> observational signal and strong mouse data — but the one human trial measured a gene-expression
> surrogate in sixteen people, and the real trial, TAME, hasn't reported. A model gives you a
> confident yes. Verdict abstains — Insufficient. And it doesn't stop there: it tells you exactly
> what would change its mind — a trial measuring the real outcome, not a surrogate. An abstention
> becomes a research directive."

### 6 · It says yes when the evidence is there — 1:56–2:10
**Screen:** Click `/#M01` (semaglutide/SELECT → Supported), then `/#C08` (ivermectin → Not Supported).

> "It's not a skeptic. Semaglutide cutting cardiovascular events in the SELECT trial — Supported.
> And the fraud case that started this — ivermectin for COVID, whose signal came from a withdrawn
> study — Not Supported. Known-bad evidence is excluded before the gate ever runs."

### 7 · Resolve your own claim, live — 2:10–2:38
**Screen:** Click the input at the top, type a fresh claim (default: *"atorvastatin lowers LDL
cholesterol in adults"*), hit **resolve**. The live console streams: parse → PubMed → each study
appearing as it's extracted → the gate. Land on the resolved card. *(Pre-recorded; cut the wait.)*

> "And none of this is pre-baked. Paste any claim, and Verdict resolves it live — Claude parses
> it, pulls the trials from PubMed and ClinicalTrials.gov, and extracts each one; you watch them
> stream in. Then the same deterministic gate issues the verdict. It's a tool you'd actually use
> — not a slideshow of our best examples."

### 8 · The honest scorecard — 2:38–2:52
**Screen:** Scroll to the scorecard: Verdict 91% / **0**, plain LLM 63% / **6**, and the live line.

> "On thirty-two real-medicine claims, the gate engine is confidently wrong zero times, against a
> plain model's six. And I'll tell you where it loses: run end-to-end from raw text, the full live
> product scores sixty-six — the honest number, reported right next to it. It errs toward humility,
> never toward a false positive. It's all in the repo."

### 9 · Close — 2:52–3:00
**Screen:** Back to a verdict card, or the header.

> "Verdict grades the state of the evidence — Supported, Not Supported, Contested, or
> Insufficient — with a full audit trail and no language model in the decision path. For the
> clinician or reviewer who needs an answer that's sourced, and honest enough to say I don't know."

---

**Lower-third to keep on screen throughout:**
*Verdict grades the state of published evidence. Research / literature-triage tool — not medical advice.*
