# Verdict — "The Duel" demo UI (Build 1)

**Date:** 2026-07-09 · **Status:** approved design, pre-implementation
**Scope:** Build 1 only — the Duel UI over the frozen demo deck. Build 2 (live backend + "paste
your own claim") is designed-for but out of scope here.

## Goal & context

Verdict competes in the hackathon's **Builder Track**, whose binding criterion is *"working
software a user could use without you in the room."* Demo is 30% of scoring and the current UI is
functional-but-flat. This build turns the app into a single, cinematic, **demo-first** screen
built to be filmed — a permanent **plain-LLM-vs-Verdict duel** whose hero moment is
**fraud-immunity** (a plain LLM confidently repeats a retracted ivermectin result; Verdict
excludes the retracted study on screen and refuses to bluff), plus a **Time Machine** that
replays the verdict through history and an **honest dual scorecard**.

No engine changes. It renders committed artifacts (`web/public/*.json`); the frozen deck is the
demo path so it can never fail on camera.

## Non-goals (Build 1)

- No live backend / live claim resolution (that is Build 2). The claim input is present but
  visually "coming soon"/disabled, not wired.
- No engine, corpus, or metric changes.
- Not pixel-perfect on mobile — target a desktop/laptop viewport (the video). Must not *break*
  on smaller widths, but desktop is the design target.

## Layout & regions (top → bottom)

1. **Masthead** — `Verdict.` wordmark + one line: *"Never confidently wrong."*
2. **Claim bar** — a row of deck chips (one per demo card; ivermectin selected by default) + a
   disabled "paste a claim…" input with a "live — coming soon" hint (Build 2 hook).
3. **The Duel** — a two-column grid, both columns always visible, sharing the selected claim:
   - **Left — "A plain LLM":** the canned confident answer bubble (`card.baseline.text`) + a
     bluff ribbon when the plain answer disagrees with the verdict.
   - **Right — "Verdict":** verdict badge + calibrated confidence → **gate trace** (cascades in)
     → the **excluded/retracted row struck through** with its integrity note (money shot) →
     a **reveal** containing the per-domain **GRADE profile** and the **full evidence ledger**
     (collapsed by default: "show all N studies").
4. **Time Machine strip** — a horizontal timeline of the selected claim's `timeline[]`: a dot per
   year, colored by verdict state, with the certainty label; the "turns" animate as the eye moves
   left→right.
5. **Scorecard strip** — the honest dual numbers in one compact band:
   `engine 91% / 0` · `live 66% / 3` · `plain-LLM 62.5% / 6`, plus one conformal line
   ("commit at High → ≤20% error, held in 93% of splits").
6. **Disclaimer** — research tool, not medical advice.

## Components (each: purpose · data · behavior)

- **`App`** — owns state: `cards: Card[]`, `evalSummary`, `liveSummary`, `conformal`, `selectedId`,
  `runKey` (re-triggers motion). Fetches `cards.json`, `eval.json`, `live_eval.json`,
  `calibration.json` on mount. Selecting a chip sets `selectedId` + bumps `runKey`.
- **`Masthead`** — static.
- **`ClaimBar`** — props: `cards`, `selectedId`, `onSelect`. Renders a chip per card (swatch =
  verdict color, truncated claim) + a disabled live input. Emits `onSelect(id)`.
- **`Duel`** — layout grid wrapping the two panels; keyed by `runKey` so a claim switch remounts
  and replays the choreography.
- **`PlainLLMPanel`** — props: `card`. Renders the baseline bubble + bluff ribbon
  (`bluffs(card)` = the plain answer contradicts the verdict).
- **`VerdictPanel`** — props: `card`. Renders badge + `card.confidence`, the claim, the
  **gate trace** (`card.gate_trace`, staggered reveal), the **ledger** (`card.ledger` via the
  existing `Row`, retracted rows struck through), and the **`GradeProfile`** + full-ledger reveal
  (collapsed). Reuses the existing `GradeProfile` component and `Row`.
- **`TimeMachine`** — props: `timeline: {year, verdict, certainty, n, changed}[]`. Horizontal
  scrubber; a colored dot per timepoint; "turns" (where `changed`) emphasized; the current/final
  state highlighted. Pure presentational.
- **`Scorecard`** — props: `evalSummary`, `liveSummary`, `conformal`. The dual-number band.
- **`Disclaimer`** — static.

## Data sources (all already committed)

- `cards.json` (per card): `verdict`, `confidence`, `baseline`, `gate_trace`, `ledger`,
  `certainty` + `certainty_start` + `certainty_domains`, **`timeline`**.
- `eval.json` → `summary.accuracy.verdict` (0.906), `confidently_wrong.verdict` (0), naive/plain.
- `live_eval.json` → `summary.accuracy` (0.656), `confident_false_positives` (3).
- `calibration.json` → `conformal` block (threshold, alpha, mean_test_error, guarantee_held_fraction).

`web/src/types.ts` extends `Card` with `timeline?: {year:number; verdict:string; certainty:string;
n:number; changed:boolean}[]` (the certainty fields are already typed).

## Motion / choreography

On mount / claim switch (`runKey` remount): (1) left bubble fades/types in (~0.5s); (2) verdict
badge lands; (3) gate-trace lines cascade (~0.3s each, existing pattern); (4) the retracted row
strikes through with emphasis; (5) confidence settles; (6) Time Machine dots reveal left→right.
Total ~3–4s — one filmable beat. Everything instant under `prefers-reduced-motion`.

## States & edge cases

- **Default:** ivermectin (C08) selected — the fraud-immunity hero.
- **Claim switch:** re-choreograph via `runKey`.
- **Missing data:** if `live_eval.json`/`conformal` fail to load, the scorecard shows the engine
  row only (graceful). A card without `timeline` hides the Time Machine strip (no crash).
- **Reduced motion / responsive:** as above.
- **Live input:** disabled, labeled "coming soon" (Build 2).

## Verification

Build with `npm run build` + `tsc --noEmit`; verify via **headless Chrome screenshots**
(`python3 -m http.server <freeport> --directory web/dist` + Chrome `--headless=new --screenshot`)
because the preview MCP is blocked by a parallel session on port 5175. Check the hero (C08), a
Supported card (M07), and the Contested trio card (M06); confirm the Time Machine + dual scorecard
render and the retracted-row exclusion is visible.

## Build order

1. `types.ts`: add `timeline`. 2. Extract `ClaimBar`, `TimeMachine`, `Scorecard`; restructure
`App.tsx` into the Duel layout. 3. CSS for the claim bar, Time Machine strip, dual scorecard, and
the reveal/choreography (extend `index.css`, keep the existing dark-glass tokens). 4. Regenerate
nothing (reads committed JSON). 5. Build + headless-verify.
