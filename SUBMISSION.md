# Methods Verifier — hackathon submission

**Built with Claude: Life Sciences · Builder track · July 7–13 2026**
Repo: https://github.com/Moe1117/verdict · Demo video: _(link)_

---

## Summary (≈185 words)

Journals now require, at submission, that a manuscript's Methods declare RRIDs for antibodies,
authentication for cell lines, and animal-rigor reporting (sex/SABV, n, randomization, blinding).
Methods Verifier is the pre-submission check for exactly that. Paste your Methods + Key-Resources
section and it returns a per-resource verdict — **PASS / FAIL / NEEDS-VERIFICATION** — each tied to
a citable public record, rolled up into a submission-ready gate.

Claude does **extraction only**; deterministic gates issue every verdict against ground truth a
model cannot fabricate: cell lines against the **ICLAC Register of Misidentified Cell Lines**,
antibodies against the **Antibody Registry** (catalog# → RRID), rigor items against ARRIVE/MDAR/SABV.
When a datum is missing it **abstains**, never guesses.

Why it needs to exist, measured: across the *entire* 594-line ICLAC register a frontier model
correctly identifies only **18%** of the contaminated lines with a documented identity (n=530, 95% CI
15–21%) and is **confidently wrong on 230**. The tool, stress-tested end-to-end through messy Methods
prose, catches **92%** (n=40, 95% CI 80–97%) and **false-flags 0 of 36** independently-chosen authentic
controls — every FAIL cited to an ICLAC ID + CVCL. It catches what a confident model gets wrong,
before Reviewer 2 does.

---

## What it does

Reads a manuscript's Methods / Key-Resources section and issues a per-resource report card:
- **Cell lines** → checked against the ICLAC misidentified-cell-line register (bundled offline).
  On the register → **FAIL**, cited with the ICLAC ID, CVCL/RRID, and the line's *true* identity.
- **Antibodies** → resolved against the Antibody Registry (catalog# → `RRID:AB_…`). Resolves →
  **PASS** with the RRID; no RRID → **NEEDS-VERIFICATION**.
- **Rigor reporting** → ARRIVE 2.0 / MDAR / NIH-SABV presence checks (sex, n, randomization, blinding).
- A missing datum → **NEEDS-VERIFICATION** (abstain), never a guess. Every finding opens an audit
  ledger: the source phrase, the registry record, and which gate fired.

The demo opens on a **frozen example** (bulletproof, served statically), and a **live lane** verifies
your own pasted Methods end-to-end. A pre-submission screening aid for professionals — **not** a
substitute for STR authentication or peer review.

## Who it's for

A **bench scientist or PI self-checking their own manuscript** before journal submission — the person
who writes and owns the Methods, and who eats the correction if a cell line turns out to be a HeLa
contaminant. Every scientist and trainee touches this; nobody memorizes the 594-entry misidentified
register.

## How we built it (with Claude)

- **Claude = structured extraction only.** From messy Methods prose it pulls a typed inventory —
  every cell line, antibody (with catalog#), and rigor fact — each carrying its verbatim source span.
  It never issues a verdict.
- **Deterministic gates decide.** Pure lookups over public ground truth: ICLAC/Cellosaurus for
  cell-line identity, the Antibody Registry for RRIDs, ARRIVE/MDAR/SABV presence rules for rigor.
  Same extract → gate → abstain → audit-ledger architecture used across this repo.
- **Calibrated abstention.** Absence of an extracted fact forces `NEEDS-VERIFICATION`, so the tool
  surfaces what a reviewer must check rather than inventing a pass.
- **Fail-proof demo, real live lane.** The ICLAC register ships as a bundled 594-line asset (no live
  dependency); the Antibody Registry is a live, key-less API. `POST /api/repro` verifies any pasted
  Methods; the frozen example is the fallback so the network can't break a demo.
- Public data only (ICLAC/Cellosaurus, Antibody Registry, ARRIVE/MDAR/NIH policy) — MIT.

## The honest scorecard

Two **separate, measured** results — never a rigged head-to-head. The first measures how unreliable a
frontier model is at this task; the second measures how well the tool works end-to-end.

**1 — A frontier model is unreliable at this task.** Bare Claude asked, for each line, "is this
misidentified, and if so what is it really?", scored over the **entire 594-line ICLAC register** (no
cherry-picking) plus **36 independently-chosen authentic control lines** — a single full-register pass
with Wilson 95% CIs (`scripts/repro_iclac_benchmark.py`, `benchmark/repro/iclac_eval.json`):

| | Bare Claude | The register |
|---|---|---|
| Correctly names a known-contaminated line (strict, n=530) | **18%** (95% CI 15–21%) | 100% completeness † |
| Confidently wrong (of the 594) | **230** | 0 |
| False-flags an authentic control line (n=36) | **0** | **0** ‡ |
| Famous (~11) vs obscure tail (519) | 91% vs **16%** | — |

† The register's "100%" is the **completeness of a lookup** — it *contains* every known misidentified
line, so it flags them all by definition. That number is not the claim; the measured, non-tautological
result is the model's 18% strict accuracy and its 230 confident errors, and the tool's end-to-end
catch below.
‡ The 36 controls are famous, unambiguously-real lines chosen by common knowledge — **not** filtered
by the tool's own verdict — so the tool's 0 false-flags is a genuine specificity measurement (its name
matching does not over-fire), not a tautology. On these easy cases the model also false-flags none; we
report only what an independent control set supports (an earlier claim that the model false-flags ~12%
rested on a non-independent control set and is withdrawn).

**2 — The tool works end-to-end on messy prose.** The register lookup is deterministic; the real risk
is that Claude fails to *extract* the line name from realistic Methods text. Stress-tested on 40
known-contaminated lines embedded in nine phrasings — clean → dense → in-a-list → hyphen-stripped
(`scripts/repro_stress_test.py`, `benchmark/repro/stress_eval.json`):

- **92% end-to-end catch** (37/40, 95% CI 80–97%) · **0 name-match misses** (the lookup held across
  every phrasing). The 3 misses were 2 genuinely bizarre non-standard names and 1 intermittent crash (a
  `None` extraction under concurrency), now hardened to degrade gracefully. (Specificity — does it
  wrongly flag an authentic line? — is measured separately above: 0 of 36 independent controls.)

## The honest boundaries (stated up front)

This audience rewards knowing exactly what you have — so:

- **We lose to a bare model on the famous cases** (it's 91% there). The edge is the ~519 obscure lines
  (model 16%) + **citability** (the tool turns "I think that's HeLa" into `ICLAC-00010 · CVCL_0372`).
- **Cell-line and antibody-identity checks are deterministic lookups** (labelled "registry"); the
  **rigor-reporting checks are model judgments** (labelled). We don't blur the two.
- **Absence from the register is not proof of identity** — STR authentication is still required, stated
  on-screen.
- **A knockout-control reasoning gate** — did the paper actually validate the antibody with a genetic
  control? — is **designed but not built**; it's the honest next step and the one place the model would
  do genuine reasoning rather than extraction.
- **Prior art:** SciScore and the Rigor & Transparency Index already run RRID + rigor checks at
  submission (some journals integrate them). Our wedge is **calibrated abstention + the audit ledger +
  the measured benchmark**, not the checklist itself.

## What's next

The knockout-control reasoning gate (grounded against real papers), a Human Protein Atlas
validation-tier gate for antibodies, and a public deploy so the tool runs without the author in the
room. The engine is validated; the numbers on screen are the numbers in `benchmark/repro/`.

---

*This repo's decidable-gates engine also powers two sibling applications built during the event — a
clinical-trial eligibility reviewer and a biomedical-evidence resolver (its prior drug-efficacy
submission is preserved in git history). Same architecture: Claude extracts, a deterministic gate
decides, it abstains when it can't, and it shows the trail.*
