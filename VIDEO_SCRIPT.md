# Verdict — 3-minute demo script

**Target:** ≤ 3:00 (paces to ~2:55). Screen recording of the web app + voiceover.
**Setup before recording:** run the web app, full-screen the browser at ~1280px wide,
zoom so a whole card fits. The app deep-links each claim by URL hash, so you can jump
straight to a tab: `/#C08`, `/#C09`, `/#F04`, `/#C01`, `/#C14`. The scorecard is at the
bottom of the page — scroll to it for the last beat.

Narration is written to be read aloud, first person. Trim a sentence anywhere you run long.

---

### 1 · The problem — 0:00–0:20
**Screen:** App open on `/#C08` (ivermectin). The left "A plain LLM" panel is visible:
a confident answer with the red ⚠ line.

> "Ask any language model whether ivermectin helps in COVID, and you get this — confident,
> fluent, and wrong. The mortality result it's echoing came from studies that were later
> withdrawn for fabricated data. The model doesn't know that. It just repeats it.
> Verdict is a second opinion that structurally can't."

### 2 · What it is, and Claude's job — 0:20–0:38
**Screen:** Pan to the right "Verdict" panel — the **Not Supported** badge, then the
"gate trace — deterministic, no LLM" heading.

> "Here Claude does exactly one job: it reads each study and pulls out the structured facts —
> design, sample size, effect, direction, risk of bias. It never makes the call.
> A deterministic gate engine makes the call. So every verdict is an auditable function of
> the evidence, not a guess dressed up as one."

### 3 · Fraud exclusion + the ledger — 0:38–1:05
**Screen:** Scroll the evidence ledger. Land on the struck-through **excluded** row
(the withdrawn Research Square preprint) and its red integrity note.

> "This is why. That row is the withdrawn preprint that drove the early positive
> meta-analyses. Verdict flags it, excludes it *before* the gate, and shows you exactly why —
> the withdrawal, the reason. What's left is the clean evidence: the large trials and
> meta-analyses that show no benefit. Verdict returns Not Supported — and every line of that
> verdict traces back to a source you can open."

### 4 · Not a one-off — 1:05–1:25
**Screen:** Click the Hydroxychloroquine tab (`/#F04`). The LLM panel parrots "Gautret et al.";
the ledger shows that same study struck through, then RECOVERY and SOLIDARITY.

> "It's not a one-off. Hydroxychloroquine — same shape. The model repeats the retracted early
> study by name. Verdict excludes it and stands on RECOVERY and SOLIDARITY, the trials that
> actually settled it. Not Supported. The fraud never reaches the verdict."

### 5 · Knowing when to abstain — 1:25–1:52
**Screen:** Click the Fenbendazole tab (`/#C09`). Verdict = **Insufficient** (blue), the
single `direct-evidence` gate reading "absence of evidence."

> "But catching fraud is the easy half. The hard half is knowing when to say *I don't know*.
> Fenbendazole for cancer: a wave of anecdotes, some cell and mouse studies, and not one
> human trial. A model hedges into a soft yes. Verdict abstains — Insufficient — because the
> human evidence to decide isn't there. Absence of evidence, stated plainly, instead of a
> guess that sounds like an answer."

### 6 · It's not just a skeptic — 1:52–2:10
**Screen:** Click Atorvastatin (`/#C01`) → **Supported**. Then Icosapent ethyl (`/#C14`)
→ **Contested**.

> "And where the evidence is solid, it says so. Atorvastatin lowering LDL — Supported.
> Where good trials genuinely disagree — omega-3 for cardiovascular events — Contested, with
> both sides on the table. Four honest states, one scale."

### 7 · The honest scorecard — 2:10–2:40
**Screen:** Scroll to the scorecard at the bottom. The table: Verdict 81% / **0**,
naive vote 77% / 0, plain LLM 74% / **2**. Then the footnote line.

> "On a blind set of 31 claims, Verdict beats a naive study-count and a plain model on
> accuracy. But that's not the headline. This column is: confidently wrong — zero, against the
> language model's two. And here's the part I'll say out loud — on emerging pipeline drugs
> with thin literature, Verdict is actually *worse* than the model, because it's conservative
> by design. We measured it, and it's in the repo. A tool you can trust has to be honest about
> where it fails, too."

### 8 · Close — 2:40–2:55
**Screen:** Back to a verdict card, or the header logo.

> "Verdict grades the state of the evidence — Supported, Not Supported, Contested, or
> Insufficient — with a full audit trail and no language model in the decision path. It's for
> the researcher asking 'is this worth six months of my life?' who needs an answer that's
> sourced, and honest enough to say I don't know. That's Verdict."

---

**One-line lower-third to keep on screen throughout:**
*Verdict grades the state of published evidence. Research/literature-triage tool — not medical advice.*
