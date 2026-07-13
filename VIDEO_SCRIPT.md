# Methods Verifier — 3-minute demo script

**Target:** ≤ 3:00. Screen recording of the web app + first-person voiceover.

**Setup — run BOTH servers so the live beats are real:**
- API: `PYTHONPATH=. .venv/bin/python -m uvicorn verdict.webapp:app --port 8011`
- UI: `VERDICT_API=http://localhost:8011 npm --prefix web run dev -- --port 5181` (the `/api` proxy points at `:8011`)
- Full-screen the browser at ~1280px. The app opens straight into the Methods Verifier — its only view —
  and loads on the **frozen demo card** + the **benchmark panel** (both render with no backend — bulletproof fallback).
- When the API is up, the header's live buttons (**Verify**, **Investigate**, **Review manuscript**)
  are enabled. If the API is down they disable and the frozen examples still show — so you can record
  the visuals even if the backend hiccups.

**Pre-record the two live beats (4b Investigate and 5 Review) separately** — the agentic loop and the
whole-manuscript review are non-deterministic run-to-run and take a few seconds. Record them cleanly
once each, then cut the wait down in the edit. The frozen `investigate_demo.json` / `review_demo.json`
are the safety net if a live take misbehaves.

Narration is first person, written to be read aloud. Word budgets are sized to the beat; trim a
sentence anywhere you run long.

---

### 1 · The problem — 0:00–0:20  *(~50 words)*
**Screen:** App open on the Methods Verifier, frozen report card visible. Cursor on the **GR-M** row —
red **FAIL**, "actually **PSN1**", cited `ICLAC-00538 · CVCL_2451`.

> "Biology papers list the exact cells and reagents they used — and sometimes a cell line is secretly
> the wrong one, a documented mix-up that quietly wrecks the results. Here, two are: GR-M isn't a
> pancreatic line, it's really a line called PSN1; SNB-19 is actually U-251 MG. Nobody can memorize the
> public register that knows this. Paste your Methods section, and you get a report card — every problem
> flagged and linked to the record that proves it — before a reviewer does."

### 2 · Why it has to exist — the benchmark — 0:20–0:48  *(~75 words)*
**Screen:** Scroll up to the **benchmark panel** — the **18%** and **92%** tiles carry the beat; the
"two different measurements — not a head-to-head" detail now sits one click down under **"Why it exists."**

> "Why not just ask a model? Because from memory, a frontier model names a contaminated line correctly
> only eighteen percent of the time — and even *flags* one as suspect only thirty-seven percent. It's
> confidently wrong on two hundred and thirty of them. It aces the dozen famous lines and collapses on
> the obscure tail — exactly where you can't eyeball it. So hand it the public register, and the only
> thing left for Claude to get wrong is reading the name out of messy prose — which holds at
> ninety-two percent."

### 3 · What Claude extracts, what the registry decides — 0:48–1:12  *(~65 words)*
**Screen:** Walk the card. **Cell lines** (FAIL, `registry` tag). **Antibodies**: **Iba1** → PASS
`RRID:AB_2665520` (`registry`); **GFAP** → NEEDS-VERIFICATION (no catalog#). Point at the **`registry`**
vs **`model judgment`** tags.

> "Here's the division of labour. Claude does the hard part a lookup can't — it pulls a typed inventory
> out of prose like 'anti-Iba1, Wako, 019-19741'. Then a *deterministic* gate decides identity: Iba1's
> catalog number resolves to a real RRID — pass. GFAP has no catalog number, so it abstains rather than
> guess. And every line is tagged: 'registry' means a lookup made the call; 'model judgment' means
> Claude did. You always know which is which."

### 4 · The reasoning beat — the knockout gate — 1:12–1:36  *(~65 words)*
**Screen:** Scroll to **Antibody validation — knockout controls (Claude reasoning)**. **Iba1** → PASS;
**GFAP** → NEEDS-VERIFICATION. Highlight the Iba1 evidence span: *"Iba1-knockout tissue… showed no
immunoreactivity."*

> "And here's the one place Claude doesn't look anything up — it *reasons*. An RRID proves an antibody
> exists, not that it was validated in *this* study. The gold standard is a genetic control — a knockout
> where the signal disappears. Claude reads the Methods and judges it: for Iba1 it found the knockout
> control and quoted it — validated. For GFAP, nothing — needs verification. A real reviewer judgment,
> labelled as one, never allowed to override the deterministic verdict."

### 4b · The agentic beat — Claude investigates the literature — 1:36–1:58  *(~60 words) — PRE-RECORDED*
**Screen:** On the **GR-M** finding, click **⚲ Investigate**. The step trail appears — *looked up
Cellosaurus → searched PubMed → fetched PMID 25877200* — then **PROVENANCE CHAIN ESTABLISHED**, citing
`CVCL_2451` and a real, **clickable** PubMed ID.

> "It can also do more than read the page — it can go find out. Click Investigate, and Claude runs its
> own bounded literature search: it queries Cellosaurus, searches PubMed, reads the record, and builds
> the provenance chain — GR-M is really a PSN1 derivative — cited to a real Cellosaurus accession and a
> real PubMed ID you can click. And the honesty is structural: it can only cite an ID a tool actually
> returned — otherwise it abstains and says so, out loud."

### 5 · The climax — review the whole manuscript, and draft the fixes — 1:58–2:42  *(~110 words) — PRE-RECORDED*
**Screen:** Above the input, click the toggle **"Review full manuscript + draft fixes."** The box is
pre-filled with a full Methods section. Click **"Review manuscript + draft fixes."** *(cut the wait)* —
the rolled-up report appears (GR-M / SNB-19 FAIL, antibodies, knockout, rigor), then scroll to the
**"Suggested corrections — drafts to paste back"** section. Rest on the **GR-M** correction, then the
**GFAP** one.

> "And this is where it stops being a checker and becomes a co-author. Switch to whole-manuscript mode
> and paste your entire Methods. It extracts every resource across the paper, runs all the gates once —
> and then Claude drafts the corrections you actually paste back. For GR-M: an STR-authentication
> sentence stating the true identity, straight from the register. For the unnamed GFAP antibody: add the
> vendor catalog number and its RRID — with a placeholder, because it will *not* invent a value it
> doesn't have. Missing sample size, blinding — the ARRIVE-compliant sentences, drafted. Every one is
> labelled a draft for you to review. It finds the problems, cites them, and hands you the fix."

### 6 · Close — 2:42–3:00  *(~45 words)*
**Screen:** Back to the top-line verdict badge + the **`registry`** / **`model judgment`** tags.

> "Methods Verifier. The deterministic gates issue every identity verdict, cited. Claude does the hard
> extraction, the one reasoning call, and the diligence — and it abstains, out loud, wherever the
> evidence isn't there. The layer that catches what a confident model gets wrong — in your Methods,
> before Reviewer 2 does."

---

**Lower-third to keep on screen throughout:**
*Methods Verifier — pre-submission reproducibility screening. Registry lookups are deterministic;
rigor, knockout-validation, and drafted corrections are labelled model judgments. Research aid, not a
substitute for STR authentication or peer review.*

**If you run long (to protect the 3:00 cap), trim in this order:** the second half of beat 4 (the
"never allowed to override" clause) → the GFAP example in beat 5 (keep GR-M + one rigor item) → the
middle sentence of beat 2. Never cut beat 5's payoff or the benchmark tiles.
