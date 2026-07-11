# Methods Verifier — 3-minute demo script

**Target:** ≤ 3:00. Screen recording of the web app + first-person voiceover.
**Setup:** run **both** servers — the API (`PYTHONPATH=. python -m uvicorn verdict.webapp:app --port
8010`) and the UI (`npm --prefix web run dev`, `:5175`) — full-screen the browser at ~1280px, and make
sure the app opens on the **Methods Verifier** tab. The page loads on the **frozen demo card**
(bulletproof, static) and the **benchmark panel** — both render with no backend.
**Live beat (scene 5):** the "Verify" button resolves a fresh pasted Methods section end-to-end (a few
seconds of real Claude extraction + reasoning + registry lookups). **Pre-record this** — the live
pipeline is non-deterministic run-to-run — and cut the wait down in the edit.

A reliable live paste (drop it in during scene 5):

> *Cells were the HEp-2 line and primary cortical neurons, maintained in DMEM/10% FBS. Sections were
> stained with anti-NeuN (Millipore, MAB377) and anti-TH (Pel-Freez, P40101); NeuN specificity was
> confirmed in NeuN-knockout brain, which showed no staining. n=6 mice per group; investigators were
> blinded to genotype.*

Narration is first person, written to be read aloud. Trim a sentence anywhere you run long.

---

### 1 · The problem — 0:00–0:25
**Screen:** App open on the Methods Verifier, showing the frozen report card. Point to the **GR-M**
row: a red **FAIL**, "actually **PSN1**", cited `ICLAC-00538 · CVCL_2451`.

> "This is a Methods section from a real-looking paper. Two of its cell lines are misidentified — GR-M
> isn't a pancreatic line, it's PSN1; SNB-19 is really U-251 MG — and nobody memorizes the 594-entry
> register that knows this. Paste your Methods here and you get a report card, before Reviewer 2 or a
> retraction does it for you. Every FAIL is cited to an ICLAC ID and a Cellosaurus accession — not a
> hunch, a record."

### 2 · Why it has to exist — the benchmark — 0:25–0:58
**Screen:** Scroll up to the **benchmark panel** — the 18% and 92% tiles + the "two different
measurements" note.

> "Why not just ask a model? Because from memory, a frontier model names a contaminated line correctly
> only eighteen percent of the time — and even just *flags* one as suspect thirty-seven percent of the
> time. It's confidently wrong on two hundred and thirty of them. It aces the dozen famous cases and
> collapses on the obscure tail — exactly where you can't eyeball it. So this isn't the model versus
> the tool; it's the model *without* the register versus the model *with* it. Give it the register, and
> the only thing left for Claude to get wrong is reading the name out of messy prose — which holds at
> ninety-two percent."

### 3 · What Claude extracts, what the registry decides — 0:58–1:30
**Screen:** Walk the report card top to bottom. Cell lines (FAIL, `registry` tag). Antibodies:
**Iba1** → PASS `RRID:AB_2665520` (`registry`); **GFAP** → NEEDS-VERIFICATION (no catalog#). Point at
the **`registry`** vs **`model judgment`** tags.

> "Here's the division of labour. Claude does the hard part a lookup can't — it pulls a typed inventory
> out of prose like 'anti-Iba1, FUJIFILM Wako, 019-19741'. Then a *deterministic* gate decides the
> identity: Iba1's catalog number resolves to a real RRID — pass; GFAP has no catalog number, so it
> abstains rather than guess. See these tags? 'Registry' means a lookup made the call. 'Model judgment'
> means Claude did. You always know which is which."

### 4 · The reasoning beat — the knockout gate — 1:30–2:05
**Screen:** Scroll to **Antibody validation — knockout controls (Claude reasoning)**. **Iba1** → PASS
"a genetic knockout control validating this antibody's specificity is described". **GFAP** →
NEEDS-VERIFICATION. Highlight the Iba1 evidence span: *"Iba1-knockout tissue… showed no
immunoreactivity"*.

> "And here's the one place Claude doesn't look anything up — it *reasons*. An RRID proves an antibody
> exists, not that it was validated in *this* study. The gold standard is a genetic control — a
> knockout showing the signal disappears. Claude reads the Methods and judges it: for Iba1 it found the
> knockout control and quoted it — validated. For GFAP there's nothing — needs verification. That's a
> real reviewer judgment, made on the text in front of it, and it's labelled a model judgment, never
> allowed to override the deterministic verdict."

### 5 · Verify your own, live — 2:05–2:40
**Screen:** Clear the box, paste the reliable Methods snippet (above), hit **Verify**. It resolves
end-to-end: HEp-2 → FAIL (cited), NeuN → the knockout gate reasons *validated*, rigor → n and blinding
detected. *(Pre-recorded; cut the wait.)*

> "None of this is pre-baked. Paste any Methods section and it runs live — Claude extracts, the
> registry decides, Claude reasons about the validation controls, and it abstains wherever it can't be
> sure. Here it catches HEp-2 as a HeLa contaminant, confirms NeuN was knockout-validated, and picks up
> that this author actually reported their sample size and blinding. A tool you'd run on your own
> manuscript — not a reel of our best examples."

### 6 · Close — 2:40–3:00
**Screen:** Back to the top-line verdict badge + the "registry / model judgment" tags.

> "Methods Verifier: the deterministic gates issue every identity verdict, cited; Claude does the hard
> extraction and the one genuine reasoning call; and it abstains, out loud, wherever the evidence isn't
> there. The layer that catches what a confident model gets wrong — in your Methods section, before
> Reviewer 2 does."

---

**Lower-third to keep on screen throughout:**
*Methods Verifier — pre-submission reproducibility screening. Registry lookups are deterministic;
rigor + knockout-validation are labelled model judgments. Research aid, not a substitute for STR
authentication or peer review.*
