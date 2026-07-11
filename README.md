# Methods Verifier — a pre-submission reproducibility check for your Methods

**Built with Claude: Life Sciences · Builder track · July 7–13 2026**
Repo: https://github.com/Moe1117/verdict · Demo video: _(link)_ · Live demo: _(link)_

A bench scientist or PI pastes their manuscript's **Methods + Key-Resources** section and gets a
per-resource report card — **PASS / FAIL / NEEDS-VERIFICATION**, each cited to a public record —
before Reviewer 2, or a post-publication correction, finds the problem.

Claude does the two things a lookup can't: it **extracts** a typed resource inventory out of messy
reagent prose, and it **reasons** about whether an antibody was validated with a genetic control.
Deterministic gates issue every *identity* verdict against ground truth a model cannot fabricate.

- **Cell lines** → the **ICLAC Register of Misidentified Cell Lines** (594 lines, bundled offline).
  On the register → **FAIL**, cited with the ICLAC ID + CVCL + the line's *true* identity.
- **Antibodies** → the **Antibody Registry** (catalog# → `RRID:AB_…`, live API). Catalog#/vendor
  must match, or it abstains — it never cites a different vendor's RRID.
- **Antibody validation (knockout controls)** → **Claude reasons** about whether the paper validated
  each antibody with a genetic knockout/knockdown/CRISPR/siRNA control (the specificity gold
  standard). A **labelled model judgment**, `PASS`/`NEEDS-VERIFICATION`, never a deterministic FAIL.
- **Investigate (agentic)** → click a flagged resource and **Claude autonomously searches PubMed +
  Cellosaurus** in a bounded loop to find whether an antibody was knockout-validated *anywhere in the
  literature* (citing the real PMID) or to build a cell line's misidentification **provenance chain**.
  **No fabricated citation IDs, by construction** — a deterministic gate keeps only citations the tools
  actually returned (whether a record *supports* the finding is a labelled model judgment), else it
  abstains (`POST /api/investigate`; measured n=30: **0 false-validation, ~⅓ class accuracy** — it abstains
  far more than it succeeds, and never wrongly validates).
- **Rigor** → ARRIVE 2.0 / MDAR / NIH-SABV presence checks (sex/SABV, n, randomization, blinding) —
  also labelled model judgments.
- A missing / unidentifiable datum → **abstains** (`NEEDS-VERIFICATION`), never guesses. Every
  finding shows its source phrase, and the report tags each check **`registry`** (deterministic) vs
  **`model judgment`** (Claude), so you always know which is which.

## Run it

```bash
pip install -e ".[web]"
PYTHONPATH=. python -m uvicorn verdict.webapp:app --port 8010   # POST /api/repro {methods}
npm --prefix web install && npm --prefix web run dev            # UI on :5175, opens on Methods Verifier
```

The UI opens on a **frozen example** (bulletproof, served statically — the demo can't fail live).
**"Verify"** runs your own pasted Methods end-to-end (Claude extraction + reasoning + registry
lookups, a few seconds), degrading back to the frozen example on any error.

> ⚕️ Pre-submission screening aid for professionals — **not** a substitute for STR authentication or
> peer review.

## Why it exists — measured, honestly

Two **separate** measurements, framed as such — never a rigged head-to-head. Reproduce with
`scripts/repro_iclac_benchmark.py` and `scripts/repro_stress_test.py`; every number ties out to
`benchmark/repro/*.json` (full scorecard in [`SUBMISSION.md`](SUBMISSION.md)).

1. **A frontier model is unreliable at this from memory.** Over the *entire* 594-line ICLAC register
   (no cherry-picking), bare Claude correctly names only **18%** of the documented-identity
   contaminated lines (n=530, 95% CI 15–21%) — and even just *flags* a line as suspect only **37%**
   of the time. It is **confidently wrong on 230** (41 at high confidence). It aces the ~11 famous
   cases (**91%**) and collapses on the 519 obscure ones (**16%**) — exactly where you can't eyeball it.
2. **Give it the register and the only failure point left is extraction — which holds.** Stress-tested
   end-to-end through nine messy phrasings, the tool's **extraction recall is 92%** (37/40, 95% CI
   80–97%) with **0 false-flags on 18 authentic controls** end-to-end (and 0/36 on the bare register
   lookup). On a catch, the identity is the *register's*, not the model's — so this measures whether
   Claude can pull the name out of prose, not whether it remembers the answer.

On the **same** task — did you flag a contaminated line at all? — the model manages 37% to the tool's
92%. That's the honest comparison; the 18-vs-92 split measures two different jobs.

## The honest boundary

- **Cell-line and antibody *identity* are deterministic lookups** (tagged `registry`). **Rigor and
  knockout-control validation are *labelled model judgments*** (tagged `model judgment`) — the
  knockout gate is the one place Claude genuinely reasons, and it never issues the deterministic
  verdict or a FAIL. It's **grounded and measured on real manuscripts**: **100% PASS-vs-NEEDS-VERIFICATION**
  on both a constructed corpus and a **21-case corpus from real open-access papers** (PMIDs cited;
  0 false-PASS, 0 missed-validated), at 67% 3-way reasoning accuracy on real text
  (`scripts/repro_knockout_eval.py`, `benchmark/repro/knockout_eval*.json`).
- The register lookup catches **98.8% of known-misidentified lines by name** (587/594): it
  deliberately **declines 7** whose entire designation is a generic lab token (AO = acridine orange,
  EPC = endothelial progenitor cells, …) rather than risk a false accusation. Specificity over
  completeness for a trust-the-citation tool.
- **Absence from the register is not proof of identity** — STR authentication is still required
  (stated on-screen).
- **Prior art:** SciScore and the Rigor & Transparency Index already run RRID + rigor checks at
  submission. Our wedge is the **offline citable register** (true identity + CVCL, not just "missing
  RRID"), **calibrated abstention**, the **knockout-control reasoning gate**, and the **measured
  benchmark** — not the checklist itself. A first measured comparison harness is in
  `scripts/repro_head_to_head.py`.

---

## Also in this repo — the same engine, two sibling apps

The decidable-gates architecture (Claude extracts → a deterministic gate decides → it abstains when
it can't → it shows the trail) also powers two other applications built during the event. **These are
not the Builder-track entry and their numbers are their own:**

- **Trial Eligibility Reviewer** — paste a free-text patient note → ranked recruiting
  ClinicalTrials.gov trials, each with a per-criterion audit ledger (`MET`/`NOT_MET`/`INSUFFICIENT`)
  that never says "eligible" while a criterion is unresolved. Opens on the **"Trial Eligibility"**
  tab; API `POST /api/match {note}`.
- **Evidence Resolver** — paste a biomedical claim → one of four evidence states with a calibrated
  confidence and an audit ledger. *Evidence Resolver:* the gate engine reproduces expert verdicts
  **91%** with 0 confident false-positives (auditability over fixed input); run end-to-end the full
  live product scores **62%** and a naive Claude scores **78%** on these famous claims; High-certainty
  is ~79–82% out-of-sample, ECE 0.16. Those figures describe the **Evidence Resolver only**, not the
  Methods Verifier. Try it: `python -m verdict "metformin reduces cancer incidence in adults without diabetes"`.

> ⚕️ These tools grade the *state of published evidence / reporting*. Research and triage aids for
> professionals — **NOT** medical advice, diagnosis, or a treatment recommendation.

## Data & attribution

Public sources only: the **ICLAC** Register of Misidentified Cell Lines + **Cellosaurus** (CVCL),
the **Antibody Registry** (RRID), **ARRIVE 2.0 / MDAR / NIH** reporting policy, and for the siblings
**PubMed** (NCBI E-utilities) and **ClinicalTrials.gov**. The tool displays citation metadata and its
own extracted rows; it does not redistribute copyrighted full text. Built from scratch during the
event (see [`PROVENANCE.md`](PROVENANCE.md)).

## License

MIT — see [`LICENSE`](LICENSE).
