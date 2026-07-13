# Methods Verifier — hackathon submission

**Built with Claude: Life Sciences · Builder track · July 7–13 2026**
Repo: https://github.com/Moe1117/verdict · Demo video: https://youtu.be/HQW0DZOr84U · Live demo: https://magenta-tartufo-666742.netlify.app

---

## Summary (100–200 words)

Journals now require that Methods declare RRIDs for antibodies, authentication for cell lines, and
animal-rigor reporting. **Methods Verifier** is the pre-submission check: paste your Methods +
Key-Resources and get a per-resource verdict — **PASS / FAIL / NEEDS-VERIFICATION** — each cited to a
public record.

Claude does the two jobs a lookup can't. It **extracts** a typed resource inventory out of messy,
hyphen-stripped prose, and it **reasons** about whether each antibody was validated with a genetic
knockout control — the specificity gold standard. Deterministic gates then issue every *identity*
verdict against ground truth a model cannot fabricate: cell lines against the **ICLAC register**,
antibodies against the **Antibody Registry**, software against **SciCrunch RRIDs**. A missing datum →
it **abstains**, cited. Every finding is tagged `registry` (deterministic) or `model judgment`
(Claude), so the two are never blurred.

Why it must exist: over the *entire* 594-line ICLAC register, a frontier model names a contaminated
line from memory only **18%** of the time — confidently wrong on **230**. Give it the register and
extraction catches **92%**; on **47 real open-access papers**, **89%** with **0 false alarms** on 14
clean controls, every FAIL cited to an ICLAC ID + CVCL.

---

## What Claude does (and where the line is)

This is a *Built with Claude* entry, so the design puts Claude where a model earns its keep and a
lookup can't reach:

1. **Hard extraction.** Real Methods prose is adversarial — "GR-M pancreatic carcinoma line",
   "anti-Iba1 (FUJIFILM Wako, 019-19741; 1:500)", multi-vendor reagent lists, hyphen-stripped names.
   Claude pulls a typed inventory (cell line, antibody + catalog#, rigor facts) with a verbatim source
   span for each. The stress test shows this is the real failure point, and it holds at **92%**.
2. **Reasoning — the knockout-control gate.** An RRID proves an antibody *exists*, not that it was
   *validated* in this study. The gold standard is a genetic control (knockout / knockdown / CRISPR /
   siRNA showing the signal disappears). Whether the Methods actually describe one — versus a bare
   "validated" claim, versus a weaker non-genetic control — is a **reasoning judgment**, and it's the
   one gate where Claude decides. It's a **labelled model judgment** (`PASS` / `NEEDS-VERIFICATION`,
   never a deterministic FAIL), and `aggregate()` never lets it fabricate the deterministic verdict.
   It is **grounded and measured on two corpora** — 16 constructed held-out cases and **21 real cases
   drawn from 6 open-access papers (PMIDs cited)**. On real manuscripts the 3-way reasoning accuracy is
   **67%** (14/21, Wilson CI 45–83%; lower than the 100% on the committed constructed run, Wilson CI 81–100% —
   real Methods are harder). But the metric that actually reaches the report card — *does it ever wrongly PASS an
   unvalidated antibody, or miss a validated one?* — is **100% on both corpora (0 false-PASS,
   0 missed-validated)** on the committed run: every real-corpus error is the invisible
   `ambiguous`↔`not_reported` confusion, and both map to `NEEDS-VERIFICATION`. (`scripts/repro_knockout_eval.py`;
   `benchmark/repro/knockout_eval*.json`; few-shot exemplars are disjoint from both eval sets.)
3. **Agentic investigation — Claude as an autonomous research agent.** The one place Claude doesn't
   just reason over the pasted text but *acts*. Click **Investigate** on a flagged resource and Claude
   runs a **bounded autonomous loop** over real public APIs (PubMed E-utilities, Cellosaurus) — it
   chooses queries, reads abstracts, chains sources — to find real-citation evidence that an antibody
   was knockout-validated *somewhere in the literature*, or to build a misidentified cell line's
   **provenance chain** (`verdict/investigate.py`, `POST /api/investigate`). **No fabricated citation IDs,
   by construction:** a deterministic gate strips any citation the tools did not actually return, so every
   cited PMID/CVCL is a real, retrieved record — whether that record *supports* the finding is a labelled
   model judgment, and it abstains when it can't ground one at all. Measured on **30 known cases**
   (`scripts/repro_investigate_eval.py`, `benchmark/repro/investigate_eval.json`): **0 false-validation on
   the committed run** — it never wrongly "validates" a reagent — at **~⅓ class accuracy**. On a realistic corpus
   it **abstains far more than it succeeds**, because antibody validation often lives in a paper's full text
   the search can't reach; where the evidence is findable it cites the right real record (anti-GABARAP 8H5 →
   `PMID:30679523`; GR-M → `CVCL_2451` + `PMID:25877200`; WiDr → `CVCL_2760`). The honest framing of the
   agentic beat: **a grounded diligence assistant that never fabricates and never false-validates** — it
   tells you when it couldn't confirm, rather than guessing.

Everything Claude touches is labelled as a model judgment; everything a **registry** decides is a pure
lookup. **The deterministic gates issue every *identity* verdict** (cell line, antibody catalog#/RRID);
rigor and knockout validation are the labelled model judgments. We never claim "no LLM in the loop" —
we claim you can always see which is which.

## The honest scorecard

Two **separate, measured** results — deliberately *not* a rigged head-to-head. Reproduce with
`scripts/repro_iclac_benchmark.py` + `scripts/repro_stress_test.py`; every number ties to
`benchmark/repro/*.json`.

**1 — A frontier model is unreliable at this from memory.** Bare Claude asked, per line, "is this
misidentified, and if so what is it really?", scored over the **entire 594-line register** (no
cherry-picking) + 36 authentic controls, Wilson 95% CIs:

| | Bare Claude (from memory) | The tool |
|---|---|---|
| Correctly **names** a contaminated line (strict, n=530) | **18%** (CI 15–21%) | identity is the register's, not recalled |
| Even just **flags** it as suspect (same task as the tool) | **37%** | **92%** end-to-end |
| Confidently wrong (of 594) | **230** (41 high, 189 medium) | 0 |
| Famous ~11 vs obscure tail 519 | 91% vs **16%** | catches the tail it can't recall |

**2 — Give it the register and the only failure point left is extraction — which holds.**
Stress-tested end-to-end through nine synthetic Methods-style phrasings (clean → dense → in-a-list →
hyphen-stripped): **92% catch** (37/40, CI 80–97%), **0 name-match misses**, and **0 false-flags on 18 controls end-to-end**
(and 0/36 on the bare register lookup — the two specificity measurements are reported separately, not
welded together). The register lookup itself catches **98.8% of known lines by name** (587/594): it
deliberately **declines 7** whose entire designation is a generic lab token (AO = acridine orange,
EPC = endothelial progenitor cells, …) rather than risk a false accusation. (The offline register file
indexes these **594 distinct lines** under **672** name-spelling keys — a line like ICLAC-00530 is
reachable under each of its documented aliases — so matching is spelling-robust; 594 is the
distinct-line count, 672 the lookup-key count.)

**Real-world slice (external validity).** The 92% is a controlled stress test; to check it in the wild we
ran the same engine over **47 real open-access Methods sections** (Europe PMC, `scripts/repro_realworld_eval.py`):
it extracted **~6 resources/paper** and, crucially, raised **0 false alarms on 14 clean controls** —
specificity holds on real papers. On the string-verifiable subset (papers whose fed Methods literally
contains a register line) it caught **16 of 18 (89%)** — essentially matching the synthetic 92%. (An early
run caught only 12/18; inspecting the misses exposed an extraction blind spot on flattened STAR / Key-Resources
*tables*, where the model would emit an empty extraction — fixed by table-aware extraction guidance + a retry
on an empty result over substantial text.) These are descriptive coverage + a *verifiable* catch/false-flag
rate, not a recall % against an unlabeled gold (that needs per-paper annotation — see What's next). WISH and
KB are excluded as probe lines (their names collide with "wish" / "kilobase" in free text).

The honest same-task comparison is **model 37%** (over all 594 register lines) **vs tool 92%** (over the
40-sentence stress corpus) on "did you flag a contaminated line"; the 18-vs-92 numbers measure two
*different* jobs (recall-the-identity vs extract-and-look-up).

## The honest boundaries (stated up front)

- **We lose to a bare model on the famous cases** (it's 91% there). Our edge is the ~519 obscure lines
  (model 16%) + **citability** (turning "I think that's HeLa" into `ICLAC-00010 · CVCL_0372`).
- **Identity checks are deterministic lookups; rigor + knockout validation are labelled model
  judgments.** We don't blur them — the report tags each finding, and the deterministic verdict is
  computed from the rule findings alone.
- **The knockout-control reasoning gate is built, grounded, and measured on real manuscripts** — 100%
  PASS-vs-NEEDS-VERIFICATION on both a constructed corpus and a 21-case real-paper corpus (0 false-PASS,
  0 missed-validated), at a 67% 3-way reasoning accuracy on real text: it
  under-distinguishes *weak* validation from *absent* validation, but never wrongly validates. Still
  **modest in scope** (single-antibody, per-paste, tens of cases); the honest next depth is a larger
  multi-annotator corpus and sharpening the `ambiguous`↔`not_reported` boundary.
- **Absence from the register is not proof of identity** — STR authentication is still required, on-screen.
- **Prior art:** SciScore and the Rigor & Transparency Index already run RRID + rigor checks at
  submission. Our wedge is the offline **citable** register (true identity + CVCL), calibrated
  abstention, the **knockout reasoning gate**, and the **measured benchmark**. A first measured
  comparison harness — the tool's obscure-tail catch that a "missing-RRID" checker doesn't cite — is
  scaffolded in `scripts/repro_head_to_head.py` (the SciScore column requires a SciScore run; we do
  not fabricate it).

## What's next

Expand the real-manuscript corpus (currently 21 PMID-anchored cases) to a larger, multi-annotator set,
sharpen the `ambiguous`↔`not_reported` boundary the real-text eval flagged, add a Human Protein Atlas
validation-tier gate, and complete the SciScore/RTI head-to-head. The engine is validated; the numbers
on screen are the numbers in `benchmark/repro/`.

---

*This repo's decidable-gates engine also powers two sibling applications built during the event — a
clinical-trial eligibility reviewer and a biomedical-evidence resolver. Their numbers (e.g. the
resolver's 91% gate / 62% live / ECE 0.16) are **theirs**, reported in the README, not the Methods
Verifier's.*
