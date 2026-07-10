import { useEffect, useRef, useState } from 'react'
import type { TrialCard, TrialCriterion, TrialDeck } from './types'

// Verdict badge class — mirrors App.tsx's badgeClass: spaces stripped so
// "Needs verification" → "b-Needsverification". CSS in index.css matches.
const trialBadgeClass = (v: string) => 'badge b-' + v.replace(/\s/g, '')

// Per-criterion result → glyph + colour class. INSUFFICIENT is the abstention state.
const RESULT_META: Record<string, { icon: string; cls: string; label: string }> = {
  MET: { icon: '✓', cls: 'met', label: 'met' },
  NOT_MET: { icon: '✗', cls: 'notmet', label: 'not met' },
  INSUFFICIENT: { icon: '❔', cls: 'insuf', label: 'not stated' },
}

// A single confident, unsourced answer — the foil. Kept generic so it still reads
// sensibly if the hero card changes. No backend call (mirrors App.tsx's BASELINES).
const FOIL =
  'Yes — she has EGFR-mutant NSCLC with progression on a prior EGFR TKI, which matches ' +
  "this trial's target population, so she appears eligible."

// Live review runs a Claude call per criterion across several trials — minutes, not seconds.
// Give the client a long leash; on timeout we keep the frozen deck rather than blank the view.
const LIVE_TIMEOUT_MS = 240_000

function ctypeTag(ctype?: string) {
  if (ctype === 'structured') return <span className="ct-tag rule">rule</span>
  if (ctype === 'semantic') return <span className="ct-tag model">model judgment</span>
  return null // missing/unknown → no tag (graceful degradation)
}

// One criterion row: icon · predicate · evidence, with a rule/model tag. Click to
// expand the source_text + the model's note.
function CriterionRow({ c }: { c: TrialCriterion }) {
  const [open, setOpen] = useState(false)
  const meta = RESULT_META[c.result] ?? RESULT_META.INSUFFICIENT
  const phrase = c.evidence_phrase?.trim() ? c.evidence_phrase : 'not stated'
  const expandable = Boolean(c.source_text?.trim() || c.note?.trim())
  return (
    <div className={'crit ' + meta.cls + (open ? ' open' : '')}>
      <button
        type="button"
        className="crit-row"
        onClick={() => expandable && setOpen((o) => !o)}
        aria-expanded={open}
        disabled={!expandable}
      >
        <span className={'crit-icon ' + meta.cls} title={meta.label}>{meta.icon}</span>
        <span className="crit-main">
          <span className="crit-pred">
            <span className={'crit-kind ' + c.kind}>{c.kind === 'exclusion' ? 'exclusion' : 'inclusion'}</span>
            {c.predicate}
          </span>
          <span className="crit-ev">
            <span className={'crit-ev-val' + (phrase === 'not stated' ? ' none' : '')}>{phrase}</span>
            {ctypeTag(c.ctype)}
          </span>
        </span>
        {expandable && <span className="crit-caret">{open ? '−' : '+'}</span>}
      </button>
      {open && expandable && (
        <div className="crit-detail">
          {c.source_text?.trim() && (
            <div className="crit-src"><span className="crit-src-label">criterion</span>{c.source_text}</div>
          )}
          {c.note?.trim() && (
            <div className="crit-note"><span className="crit-src-label">reasoning</span>{c.note}</div>
          )}
        </div>
      )}
    </div>
  )
}

function TrialCardView({ card, hero }: { card: TrialCard; hero: boolean }) {
  const ledger = (
    <>
      <div className="section-label">eligibility ledger — one line per criterion, each traced to its source text</div>
      <div className="crit-list">
        {card.criteria.map((c) => (
          <CriterionRow key={c.id} c={c} />
        ))}
      </div>
    </>
  )

  return (
    <div className={'tcard' + (hero ? ' hero' : '')}>
      <div className="tcard-head">
        <div className="tcard-title-wrap">
          <a className="tcard-nct" href={card.url} target="_blank" rel="noreferrer">{card.nct_id}</a>
          <span className="tcard-status">{card.status}</span>
        </div>
        <span className={trialBadgeClass(card.verdict)}>{card.verdict}</span>
      </div>
      <a className="tcard-title" href={card.url} target="_blank" rel="noreferrer">{card.title}</a>
      <div className="tcard-counts">
        <span className="tc-count met">{card.n_met} met</span>
        <span className="tc-sep">·</span>
        <span className={'tc-count' + (card.n_disqualifying > 0 ? ' disq' : '')}>{card.n_disqualifying} disqualifying</span>
        <span className="tc-sep">·</span>
        <span className="tc-count verify">{card.n_to_verify} to verify</span>
      </div>

      {hero ? (
        // Foil pane — a bare LLM vs. the ledger, side by side. The contrast is the point.
        <div className="foil">
          <div className="foil-pane bare">
            <div className="panel-label">A bare model</div>
            <div className="who"><span>🤖</span> <b>Assistant</b></div>
            <div className="bubble">{FOIL}</div>
            <div className="foot">no per-criterion check · cannot abstain · no source</div>
          </div>
          <div className="foil-pane ledger">
            <div className="panel-label">Trial reviewer</div>
            {ledger}
          </div>
        </div>
      ) : (
        ledger
      )}

      {card.to_verify.length > 0 && (
        <div className="directive abstain verify-list">
          <span className="dir-label">
            open questions — {card.to_verify.length} item{card.to_verify.length === 1 ? '' : 's'} the note can't decide
          </span>
          <ul className="vl-items">
            {card.to_verify.map((v, i) => (
              <li key={i} className="vl-item"><span className="vl-box" />{v.replace(/^Confirm:\s*/i, '')}</li>
            ))}
          </ul>
        </div>
      )}

      {hero && (
        <div className="foil-caption">
          a bare model just answers; this one shows every criterion and abstains when the note can't decide.
        </div>
      )}
    </div>
  )
}

export default function TrialMatch() {
  const [deck, setDeck] = useState<TrialDeck | null>(null)
  const [note, setNote] = useState('')
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // On mount: load the frozen deck. It's instant and bulletproof — this is what gets demoed.
  // Pre-fill the textarea with the deck's note so "Review trials" has something to send.
  useEffect(() => {
    fetch('/trialdeck/case1.json')
      .then((r) => r.json())
      .then((d: TrialDeck) => {
        setDeck(d)
        setNote((cur) => cur || d.note)
      })
      .catch(() => setError('Could not load the saved trial deck.'))
  }, [])

  // Live review: POST the note to /api/match with a long client timeout. On success, swap in the
  // live deck; on error OR timeout, keep the frozen deck showing (never blank the view).
  const review = () => {
    const n = note.trim()
    if (n.length < 3 || state === 'loading') return
    const ctrl = new AbortController()
    abortRef.current = ctrl
    const timer = setTimeout(() => ctrl.abort(), LIVE_TIMEOUT_MS)
    setState('loading')
    setError(null)
    fetch('/api/match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: n }),
      signal: ctrl.signal,
    })
      .then((r) => {
        if (!r.ok) throw new Error(`server returned ${r.status}`)
        return r.json()
      })
      .then((d: TrialDeck) => {
        if (d && Array.isArray(d.cards)) setDeck(d)
        setState('idle')
      })
      .catch((e) => {
        setError(
          e?.name === 'AbortError'
            ? 'Live review timed out — the saved deck below still works.'
            : 'Live review failed (is the API running on :8010?). The saved deck below still works.',
        )
        setState('error')
      })
      .finally(() => clearTimeout(timer))
  }

  const cards = deck?.cards ?? []

  return (
    <div className="trialmatch">
      <div className="tm-sub">
        Paste a patient note → ranked recruiting trials, each with a per-criterion audit ledger.
        It abstains when the note can't decide and hands you the checklist.
      </div>

      <div className="tm-input">
        <textarea
          className="tm-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Paste a free-text patient note — e.g. “62-year-old woman with metastatic EGFR exon-19-deletion NSCLC, progressed on first-line osimertinib. ECOG 1.”"
          rows={3}
          disabled={state === 'loading'}
          aria-label="Patient note"
        />
        <div className="tm-actions">
          <button
            type="button"
            className={'tm-run' + (state === 'loading' ? ' busy' : '')}
            onClick={review}
            disabled={note.trim().length < 3 || state === 'loading'}
          >
            {state === 'loading' ? (<><span className="lc-spin" /> reviewing…</>) : 'Review trials'}
          </button>
          <span className="tm-caption">
            Live review runs a Claude call per criterion — it can take a few minutes, and live retrieval is
            best-effort. The saved deck below is the reliable path.
          </span>
        </div>
        {error && <div className="tm-error">⚠ {error}</div>}
      </div>

      {cards.length > 0 ? (
        <div className="tm-deck">
          {cards.map((c, i) => (
            <TrialCardView key={c.nct_id} card={c} hero={i === 0} />
          ))}
        </div>
      ) : (
        !error && <div className="tm-loading"><span className="lc-spin" /> loading saved deck…</div>
      )}

      <div className="disclaimer">
        <b>This ranks recruiting trials by how the note maps to each eligibility criterion.</b> It is a
        research and screening-triage aid for professionals — not medical advice, not an enrollment decision,
        and never a substitute for a study coordinator's and principal investigator's review of the full protocol.
      </div>
    </div>
  )
}
