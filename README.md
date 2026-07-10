# Verdict

**A decidable evidence resolver for biomedical claims — one that reports when the evidence is insufficient to decide.**

Paste a claim like *"metformin reduces cancer incidence in adults without diabetes"* and Verdict returns one of four evidence states — **Supported · Not Supported · Contested · Insufficient** — with a calibrated confidence and a full audit ledger tracing every study to the gate it fed. When the evidence cannot decide, Verdict **abstains** rather than overstate.

> ⚕️ **Verdict grades the state of published EVIDENCE for a claim. It is a research and literature-triage tool for professionals. It is NOT medical advice, NOT a diagnosis, and NOT a treatment recommendation.**

Built for the **Built with Claude: Life Sciences** hackathon (Builder track), July 7–13 2026.

---

## Trial Eligibility Reviewer — the Builder-track entry

The submission applies the same decidable-engine idea (**Claude extracts, a deterministic aggregator decides**) to a sharper, named-user decision: **patient ↔ clinical-trial eligibility**. The evidence-resolver sections below document the shared engine and its calibration.

**Named user:** a **clinical research coordinator** screening a patient against open trials. They paste a free-text patient note and get back **ranked recruiting ClinicalTrials.gov trials**, each with a **per-criterion audit ledger** — every inclusion/exclusion criterion marked `MET` / `NOT_MET` / `INSUFFICIENT`, tied to the exact phrase in the note — plus a verdict (`Likely eligible` / `Ineligible` / `Needs verification`). The verdict **never says eligible while any criterion is unresolved**: it **abstains** (`Needs verification`) and hands back a **to-verify checklist** of exactly what the note can't decide.

**The differentiator — and the honest boundary.** Claude does two extraction jobs (patient facts from the note; each trial's eligibility text into structured criteria). The **verdict is a deterministic aggregation** of the per-criterion results — no LLM chooses it (any exclusion `MET` or inclusion `NOT_MET` → Ineligible; all clear → Likely eligible; anything unresolved → Needs verification). **Structured criteria** (age, ECOG, lab thresholds) are decided by pure comparators, labelled **`rule`** in the UI; **semantic criteria** (e.g. *"measurable disease per RECIST"*) are **Claude judgments**, labelled **`model judgment`**, deliberately biased to `INSUFFICIENT` when the note is silent so the system abstains rather than guess. The honest scope is therefore narrow and stated on-screen: *the aggregation and the structured comparisons are deterministic and auditable; the semantic reads are labelled model judgments that abstain on silence.* We do **not** claim there is no LLM in the decision, and the evidence-resolver's conformal guarantee does **not** transfer to this task.

**Run it:**

```bash
pip install -e ".[web]"
python -m uvicorn verdict.webapp:app --port 8010        # live API — POST /api/match {note}
npm --prefix web install && npm --prefix web run dev     # UI on :5175, opens on the "Trial Eligibility" tab
```

The UI opens on a **frozen demo deck** (a real end-to-end run, served statically from `web/public/trialdeck/` so the demo can't fail live). **"Review trials"** runs a live review of a pasted note — a Claude call per criterion, so minutes, best-effort — and falls back to the frozen deck on error or timeout.

> ⚕️ Research and screening-triage aid for professionals — **not** medical advice, **not** an enrollment decision, and never a substitute for a study coordinator's and principal investigator's review of the full protocol.

<details><summary><b>Submission blurb (≈150 words)</b></summary>

A clinical research coordinator pastes a free-text patient note; the Trial Eligibility Reviewer returns ranked recruiting ClinicalTrials.gov trials, each with a per-criterion audit ledger — every inclusion/exclusion criterion marked MET, NOT_MET, or INSUFFICIENT and tied to the exact phrase in the note — and a verdict that never says "eligible" while anything is unresolved. Instead it abstains ("Needs verification") and hands back a to-verify checklist of what the note can't decide. Claude does the extraction (patient facts; each trial's eligibility text into structured criteria); a deterministic aggregator issues the verdict — no LLM picks it. Structured criteria (age, ECOG, labs) are decided by pure comparators and labelled "rule"; semantic criteria are labelled "model judgment" and biased to abstain on silence. The result counter-positions an ML-heavy field on deterministic auditability and calibrated abstention: it tells a coordinator not just *which* trials, but *exactly what to verify* before acting.

</details>

## Who it's for

A translational researcher or early-stage biotech scientist triaging a drug-efficacy or drug-repurposing hypothesis — *"is this worth six months?"* — who needs a sourced, rigorous verdict, including an explicit determination that the evidence is not yet sufficient.

## The idea (and why the architecture matters)

Claude does one job: **structured extraction** of evidence from each study (design, N, effect, direction, risk-of-bias). A **deterministic gate engine — with no LLM in the verdict path — issues the verdict.** That means every verdict is a pure, auditable function of the evidence: you can click any verdict and see exactly which studies drove it and which gate each one passed. A calibration layer reports the empirically-measured — and measurably imperfect — reliability of each certainty grade.

This is selective prediction with a measured reject option: certainty is an ordinal grade whose out-of-sample accuracy is measured (High-certainty is ~79% on the original held-out set and ~82% across all held-out claims, ECE 0.16), backed by a distribution-free conformal error bound at High, and it abstains where it cannot be relied upon.

**How well does it work? — the honest numbers.** The deterministic **gate engine** reproduces expert-adjudicated verdicts 91% of the time with 0 confident false-positives on 32 clinical claims (holding extraction fixed — an auditability result over structured input, not external accuracy — independently, a cross-check of 12 gold labels against external landmark RCTs/meta-analyses/FDA actions agreed 12/12, `benchmark/gold_external_audit.json`). Run **end-to-end from raw claims**, the **full live product** scores 62% and abstains on 19% rather than overstate. A strong naive Claude already scores 78% on these famous claims — we do **not** claim to beat it there; Verdict's edge is that it is sourced, calibrated, abstains, and won't reproduce a fraud-driven result. See [`SUBMISSION.md`](SUBMISSION.md); reproducible (`scripts/build_eval_dataset.py`, `scripts/live_benchmark.py`, `scripts/live_baseline.py`).

## Evidence states

| State | Meaning |
|-------|---------|
| **Supported** | Consistent high-quality evidence (RCTs / meta-analyses) shows the claimed effect |
| **Not Supported** | Sufficient high-quality evidence shows *no* effect / contradicts it (evidence of absence) |
| **Contested** | High-quality evidence genuinely conflicts and doesn't resolve |
| **Insufficient** | Not enough human evidence to decide (absence of evidence) |

`Undecidable` exists only as an *input guard* for ill-posed / unmeasurable claims — not as an evidence verdict.

## Data & attribution

Retrieval uses public sources only:
- **PubMed** via NCBI E-utilities — see the NCBI [disclaimer and usage policy](https://www.ncbi.nlm.nih.gov/home/about/policies/).
- **ClinicalTrials.gov** API — U.S. Government work, public domain.

Verdict displays citation metadata (title, authors, journal, year, PMID/DOI/NCT) and its own extracted structured rows; it does not redistribute copyrighted full text.

## Provenance

See [`PROVENANCE.md`](PROVENANCE.md). Built from scratch during the event; no pre-existing code, data, or benchmark reused.

## Quickstart

```bash
cp .env.example .env       # add your ANTHROPIC_API_KEY and NCBI_EMAIL
pip install -e .
python -m verdict "metformin reduces cancer incidence in adults without diabetes"
```

### Live demo — the web UI + resolve-your-own-claim API

The demo has two lanes: a **frozen deck** (pre-resolved cards, served statically — the demo can
never fail live) and a **live lane** that resolves a pasted claim end-to-end (Claude parse →
PubMed + ClinicalTrials.gov retrieval → Claude extraction → deterministic gates, ~40s).

```bash
pip install -e ".[web]"                                   # fastapi + uvicorn
python -m uvicorn verdict.webapp:app --port 8010          # the live API (reads .env)
npm --prefix web install && npm --prefix web run dev      # the UI on :5175 (proxies /api -> :8010)
```

Then open the UI, or hit the API directly:

```bash
curl -s localhost:8010/api/health
curl -sN "localhost:8010/api/resolve/stream?claim=semaglutide%20reduces%20body%20weight%20in%20adults%20with%20obesity"
```

`GET /api/resolve/stream` streams the pipeline as Server-Sent Events (each retrieved study appears
as it is extracted), then the final gated card. `POST /api/resolve {claim}` returns the same card
synchronously. The verdict is still a pure function of the extracted evidence — no LLM in the
verdict path. To serve everything from one process, build the UI first
(`npm --prefix web run build`); then `uvicorn verdict.webapp:app` also serves it from `web/dist`.

## License

MIT — see [`LICENSE`](LICENSE).
