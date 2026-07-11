# Design — The Agentic Investigator (podium bet)

**Date:** 2026-07-11 · **Status:** approved design, spec under review · **Branch:** `feat/podium-investigator` (off shipped `dc1a340`)

## Goal

Earn a **second winner-grade (8+) axis** for the Methods Verifier hackathon entry so it can reach the
Builder-track podium. Four re-judge passes agree: **Depth is already 8.0**, but **Claude Use (7.1)** and
**Impact (6.5)** cap the score — Claude Use because the tool is "a single, well-evaluated classifier
call, not an agentic capability that surprises Anthropic." This design adds the missing thing: a
**genuinely agentic capability** where Claude autonomously does diligent-reviewer legwork **no lookup
can** — live across the public literature — while preserving the no-fabrication honesty discipline that
has kept every prior number credible.

Two phases, sequenced by leverage:
- **Phase 1 (primary): the Agentic Investigator** — the Claude Use lever.
- **Phase 2 (secondary, if time): whole-manuscript ingestion + auto-fix** — the Impact/Demo lever.

Non-goals / YAGNI: no new registries beyond PubMed + Cellosaurus + the Antibody Registry; no account
system; no writing to any external system; Phase 2 only if Phase 1 lands and is measured.

---

## Phase 1 — The Agentic Investigator

### Capability

A new **deep** action (separate from the fast `/api/repro`): given one flagged resource, Claude runs a
**bounded, autonomous investigation** across real public APIs and returns a verdict **grounded in real
citations** — or abstains.

- **Antibody** → Claude searches the literature for whether this antibody (by target / RRID / catalog#)
  was ever **knockout / knockdown / CRISPR / siRNA validated anywhere**, reads real abstracts (and PMC
  open-access full text for top candidates), and returns **FOUND_VALIDATION** citing a real **PMID**, or
  **NO_VALIDATION_FOUND** (honest abstention after a real search).
- **Cell line (flagged on ICLAC)** → Claude builds a cited **provenance chain**: the ICLAC record → the
  **Cellosaurus** entry (CVCL) → the **primary reference** (real PMID) that first documented the
  misidentification.

This turns the tool from "grade the pasted text" into "**investigate the resource across the
literature like a reviewer would**" — the agentic reveal.

### Architecture

New module `verdict/investigate.py`. **No MCP** — the app calls real HTTP APIs directly (as it already
does for the Antibody Registry):
- **NCBI E-utilities** — `esearch` (query → PMIDs), `esummary`/`efetch` (PMIDs → title/abstract/year).
  Keyless; uses `NCBI_EMAIL` (already in `.env.example`) + polite rate limiting.
- **Cellosaurus REST API** (`api.cellosaurus.org`) — cell-line record → CVCL, problems, references.
- **The Antibody Registry** — already wired in `repro.check_antibody`.

**The bounded agentic loop.** Claude drives the investigation via the Anthropic tool-use API in a loop:
it is given tool definitions `pubmed_search(query)`, `pubmed_fetch(pmids)`, `cellosaurus_lookup(name)`,
reasons, calls a tool, receives the **real** result, reasons again, and finishes by calling a forced
final tool `emit_investigation(verdict, cited_ids, reasoning, steps_summary)`. Caps: **≤3 searches,
≤6 fetches, ≤8 total steps** (cost, latency, demoability). Claude chooses the queries and when to stop
— genuine autonomy.

**The honesty anchor (load-bearing).** A `Retriever` object logs every ID any tool actually returned
into a `retrieved` set. When Claude emits its verdict, `investigate.py` **deterministically filters
`cited_ids` to those present in `retrieved`** — any ID Claude produced from memory is stripped. If a
"found" verdict has no surviving citation, it is **downgraded to abstain** ("could not ground this in
retrieved literature"). Claude navigates; a deterministic gate decides what may be cited. Same
philosophy as the existing extract→gate→abstain engine, extended to an agent.

### Components & interfaces

- `verdict/investigate.py`
  - `Retriever` — wraps the three HTTP APIs; every call returns real records AND records their IDs in
    `retrieved`. One clear job: real retrieval + provenance logging.
  - `investigate_antibody(name, target, catalog, rrid) -> Investigation`
  - `investigate_cell_line(name, iclac_id, cvcl) -> Investigation`
  - `Investigation` dataclass: `{kind, verdict, cited: [{id, kind, title, why}], reasoning, steps: [str], grounded: bool}`.
    `verdict ∈ {FOUND_VALIDATION, NO_VALIDATION_FOUND, PROVENANCE_CHAIN, PARTIAL, INCONCLUSIVE}`.
    Labeled `method = "model investigation"` (distinct from `rule` and `model judgment`).
- `verdict/webapp.py` — `POST /api/investigate {kind, name, target?, catalog?, rrid?, cvcl?, iclac_id?}`
  → the `Investigation` as JSON, including `steps` (the agentic trail, for the UI). Spend-guarded via the
  existing `_daily_gate()` + concurrency slot; degrades gracefully on any error (never 502).
- `web/src/Repro.tsx` — an **"Investigate"** affordance on a flagged resource; renders the agentic
  `steps` (searched → found → reading → concluded) then the cited result. `VITE_API_BASE`-aware.

### Data flow

flagged resource → `/api/investigate` → `investigate.py` builds the `Retriever` + tool defs → bounded
Claude tool-use loop (search/fetch/lookup against real APIs, ≤ caps) → Claude emits verdict + cited_ids
→ deterministic citation-verification against `Retriever.retrieved` → grounded `Investigation` → JSON
(verdict + real citations + steps) → UI renders the trail + the cited paper.

### How it is measured (a proven capability, not a demo trick)

`benchmark/repro/investigate_corpus.json` — known-answer cases:
- **Antibodies with published KO/KD validation** (real, several already in `knockout_corpus_real.json`,
  e.g. GABARAP-8H5 → its validating paper PMID; the AKT1 Proteintech siRNA case) → expect
  FOUND_VALIDATION citing the correct real PMID.
- **Misidentified lines** with a known primary-misidentification reference in Cellosaurus/ICLAC → expect
  a PROVENANCE_CHAIN citing the correct real PMID/CVCL.
- **Negative controls** — an antibody with no published genetic validation, or a nonsense target →
  expect NO_VALIDATION_FOUND (correct abstention).

`scripts/repro_investigate_eval.py` reports: **found-correct rate** (cited the right real record),
**false-citation rate** (cited something that does NOT support the claim — must be ~0, the costly
error), and **abstention correctness**, each with **Wilson 95% CIs**, reproducible across runs (the
model has no temperature param — report across-run stability). This is the number that makes it a
measured capability the judges reward, not a scripted reel.

### Honesty & safety

- **No fabricated citations, ever** — deterministic verification against real retrieval; abstain otherwise.
- **Labeled** `model investigation` in the report + UI; it never issues a deterministic identity verdict
  and never flips `/api/repro`'s headline (which stays rule-only).
- **Bounded spend** — the daily cap + concurrency slot extend to `/api/investigate`; per-call step caps.
- **Rate/etiquette** — NCBI email + throttling; Cellosaurus polite use; all sources public + citable.

### Testing (TDD)

Unit tests mock the `Retriever` (like the knockout tests mock `call_tool`): (1) a cited ID absent from
`retrieved` is stripped and a "found" verdict downgrades to abstain; (2) the loop respects the step
caps; (3) an antibody whose retrieval contains a real KO-validation abstract → FOUND_VALIDATION citing
that ID; (4) a cell line whose Cellosaurus record carries a misidentification reference → PROVENANCE_CHAIN;
(5) any tool exception → graceful INCONCLUSIVE, never a crash. Offline suite stays green; the live eval
is a separate script.

---

## Phase 2 (secondary, if Phase 1 lands + is measured) — Whole-manuscript + auto-fix

Lighter scope, the Impact/Demo lever:
- **Ingest** a full Methods/manuscript text (raise the length cap; chunk if needed), extract *every*
  resource, run all gates + investigations → a complete pre-submission rigor report.
- **Auto-fix** — Claude drafts submission-ready corrections for each finding (the correct RRID, the true
  cell-line identity + an STR-authentication sentence, the missing ARRIVE/MDAR rigor statements) → a
  revised Methods block the author can paste back. Labeled a draft, human-review required.

Only specced in detail if Phase 1 is done and measured before the deadline.

---

## Risks (honest)

- **Coverage:** antibody validation often lives in full-text Methods, not abstracts → the agent will
  *honestly abstain* fairly often; the cell-line provenance chain is the more reliably-impressive half.
  Mitigation: search abstracts + fetch PMC open-access full text for top candidates; accept abstention.
- **Latency/cost/wander:** agentic loops are slow, paid, and can drift → hard caps + citation-verification.
- **API friction:** NCBI/Cellosaurus rate limits or downtime → graceful degradation + a frozen demo case.
- **No podium guarantee:** best case lifts Claude Use toward 8+ (and Impact/Demo a little); realistically
  the strongest shot, not a sure thing. This is an explicit bet.

## Success criteria

1. `investigate.py` runs a real, bounded, autonomous multi-tool loop and returns **grounded** verdicts
   (0 fabricated citations by construction), wired into an `/api/investigate` endpoint + a UI trail.
2. A measured investigator eval with CIs on known cases: high found-correct on the positives,
   **~0 false-citation**, correct abstention on negatives — reproducible across runs.
3. Offline test suite stays green; spend-guarded; degrades gracefully.
4. (Stretch) Phase 2 whole-manuscript + auto-fix.

## Out of scope

Multi-annotator corpus expansion; new registries; verbatim-corpus rebuild; any write to external
systems; auth. The shipped 7.17 entry on `fix/mv-p0-hardening` @ `dc1a340` remains the untouched fallback.
