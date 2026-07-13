import { useEffect, useRef, useState } from 'react'
import type { Correction, IclacBench, Investigation, ManuscriptReport, ReproDeck, ReproFinding, ReproReport } from './types'

// Verdict badge class — like App.tsx's badgeClass, but strips spaces AND hyphens so
// "Submission-ready" → "b-Submissionready", "Needs fixes" → "b-Needsfixes". CSS matches.
const reproBadgeClass = (v: string) => 'badge b-' + v.replace(/[\s-]/g, '')

const pct = (x: number) => Math.round(x * 100 - 1e-9) + '%'  // round-half-down so 92.5% shows as 92%, matching the docs

// The live "Verify" lane calls the API. On a static deploy the API lives on a DIFFERENT origin, so
// prefix /api/* with VITE_API_BASE (empty in dev → same-origin via the Vite proxy). Static assets
// (/repro/*.json) always stay same-origin with the frontend, so they are NOT prefixed.
const API_BASE = (((import.meta as any).env?.VITE_API_BASE as string | undefined) ?? '').replace(/\/+$/, '')
const api = (path: string) => API_BASE + path

// Per-finding result → glyph + colour class. INSUFFICIENT is the abstention state.
const RESULT_META: Record<string, { icon: string; cls: string; label: string }> = {
  FAIL: { icon: '✗', cls: 'fail', label: 'fail' },
  PASS: { icon: '✓', cls: 'pass', label: 'pass' },
  INSUFFICIENT: { icon: '❔', cls: 'insuf', label: "can't verify — check manually" },
}

// Findings render grouped by kind, in this order. Anything else falls through to "Other checks".
const KIND_GROUPS: { kind: string; label: string }[] = [
  { kind: 'cell_line', label: 'Cell lines' },
  { kind: 'antibody', label: 'Antibodies' },
  { kind: 'knockout', label: 'Antibody proven specific? — a "knockout" control deletes the target gene · Claude\'s reasoning' },
  { kind: 'software', label: 'Software & tools' },
  { kind: 'rigor', label: 'Rigor reporting — sample size, blinding, animal sex' },
]

// Live verify runs one Claude extraction + registry lookups — seconds. Give a generous leash;
// on timeout OR error we keep the frozen demo showing rather than blank the view.
const LIVE_TIMEOUT_MS = 120_000

// method → provenance tag. "rule" is a deterministic registry lookup; "model judgment" is Claude.
// Unknown/absent → no tag (graceful degradation).
function methodTag(method?: string) {
  if (method === 'rule') return <span className="rp-tag rule">registry</span>
  if (method === 'model judgment') return <span className="rp-tag model">model judgment</span>
  return null
}

// Render a detail string, turning **bold** markers into <strong>. Anything outside the
// markers is plain text. Handles zero, one, or many spans.
function renderDetail(detail: string) {
  return detail.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <span key={i}>{part}</span>,
  )
}

// Agentic-investigation verdict -> label + tone class (reuse the pass/insuf colours).
const INV_META: Record<string, { label: string; cls: string }> = {
  FOUND_VALIDATION: { label: 'validated elsewhere in the literature', cls: 'pass' },
  PROVENANCE_CHAIN: { label: 'mix-up confirmed — paper trail traced', cls: 'pass' },
  PARTIAL: { label: 'partly grounded — verify', cls: 'insuf' },
  NO_VALIDATION_FOUND: { label: 'no validation found — verify', cls: 'insuf' },
  INCONCLUSIVE: { label: 'investigation inconclusive', cls: 'insuf' },
}

function citeHref(id: string): string | null {
  if (id.startsWith('PMID:')) return `https://pubmed.ncbi.nlm.nih.gov/${id.slice(5)}/`
  if (id.startsWith('CVCL_')) return `https://www.cellosaurus.org/${id}`
  return null
}

// Build the /api/investigate request from a finding (parse the name + any CVCL/ICLAC/RRID from its citation).
function buildInvReq(f: ReproFinding) {
  const name = f.item.replace(/^(cell line|antibody|antibody validation):\s*/i, '').trim()
  const cite = f.citation || ''
  if (f.kind === 'cell_line') {
    return { kind: 'cell_line', name,
             cvcl: (cite.match(/CVCL_\w+/) || [''])[0], iclac_id: (cite.match(/ICLAC-\d+/) || [''])[0] }
  }
  return { kind: 'antibody', name, target: name, rrid: (cite.match(/RRID:AB_\w+/) || [''])[0] }
}

// The agentic investigation: the step trail (searched -> read -> concluded), then the grounded verdict
// + REAL citations (every id is deterministically verified against actual retrieval — no fabrication).
function InvestigationView({ inv }: { inv: Investigation }) {
  const meta = INV_META[inv.verdict] ?? INV_META.INCONCLUSIVE
  return (
    <div style={{ marginTop: 8, paddingLeft: 10, borderLeft: '2px solid var(--border, #333)' }}>
      <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, color: 'var(--text-muted,#8a8a8a)' }}>
        Claude investigated the literature
      </div>
      <ol style={{ margin: '4px 0 8px', paddingLeft: 18, fontSize: 12.5, color: 'var(--text-muted,#8a8a8a)', lineHeight: 1.55 }}>
        {inv.steps.map((s, i) => <li key={i}>{s}</li>)}
      </ol>
      <div className={'rp-tag ' + (meta.cls === 'pass' ? 'rule' : 'model')} style={{ fontSize: 12.5 }}>
        {meta.label}
      </div>
      {inv.reasoning && <div style={{ fontSize: 12.5, margin: '6px 0', lineHeight: 1.5 }}>{inv.reasoning}</div>}
      {inv.cited.length > 0 && (
        <div style={{ fontSize: 12.5 }}>
          {inv.cited.map((c) => {
            const href = citeHref(c.id)
            return (
              <div key={c.id} style={{ margin: '2px 0' }}>
                {href ? <a href={href} target="_blank" rel="noreferrer"><b>{c.id}</b></a> : <b>{c.id}</b>}
                {c.title && <span style={{ color: 'var(--text-muted,#8a8a8a)' }}> — {c.title}</span>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// One finding row: result icon · item · citation badge · provenance tag, then the detail verdict, the
// verbatim manuscript evidence, and (for cell lines / antibodies) an agentic "Investigate" affordance.
function FindingRow({ f, onInvestigate, inv, busy, invError }: {
  f: ReproFinding
  onInvestigate?: (f: ReproFinding) => void
  inv?: Investigation
  busy?: boolean
  invError?: string
}) {
  const meta = RESULT_META[f.result] ?? RESULT_META.INSUFFICIENT
  const cite = f.citation?.trim()
  const ev = f.evidence?.trim()
  const canInvestigate = onInvestigate && (f.kind === 'cell_line' || f.kind === 'antibody')
  return (
    <div className={'rp-find ' + meta.cls}>
      <span className={'rp-icon ' + meta.cls} title={meta.label}>{meta.icon}</span>
      <div className="rp-find-body">
        <div className="rp-find-top">
          <span className="rp-item">{f.item}</span>
          {cite && <span className="rp-cite" title="Citation to the public record — ICLAC/CVCL = cell-line register + database IDs · RRID = a reagent's unique ID">{cite}</span>}
          {methodTag(f.method)}
          {canInvestigate && !inv && (
            <button type="button" onClick={() => onInvestigate!(f)} disabled={busy}
              style={{ marginLeft: 'auto', fontSize: 11.5, padding: '2px 8px', cursor: busy ? 'default' : 'pointer',
                       border: '1px solid var(--border,#333)', borderRadius: 5, background: 'transparent',
                       color: 'inherit', opacity: busy ? 0.6 : 1 }}>
              {busy ? <><span className="lc-spin" /> investigating…</> : '⚲ Investigate'}
            </button>
          )}
        </div>
        <div className="rp-detail">{renderDetail(f.detail)}</div>
        {ev && <div className="rp-ev">{ev}</div>}
        {invError && <div className="tm-error" style={{ marginTop: 6 }}>⚠ {invError}</div>}
        {inv && <InvestigationView inv={inv} />}
      </div>
    </div>
  )
}

// The benchmark panel — TWO separate measured facts, honestly framed as such (NOT a head-to-head):
// how unreliable a frontier model is from memory, and how well extraction holds end-to-end on prose.
function BenchmarkPanel({ bench }: { bench: IclacBench }) {
  const { model, tool, examples, realworld } = bench
  const flagRecall = model.flag_recall != null ? pct(model.flag_recall) : null
  const ctrlN = tool.n_controls_endtoend ?? tool.n_controls
  const ctrlFF = tool.false_flags_endtoend ?? tool.false_flags
  return (
    <div className="rp-bench">
      <div className="panel-label">The benchmark</div>
      <div className="rp-bench-headline">
        Asked to name a contaminated line from memory, a frontier model gets it right only{' '}
        <b className="bad">{pct(model.strict_accuracy)}</b> of the time
        {flagRecall && <> — and even just <i>flags</i> the line at all <b className="bad">{flagRecall}</b> of the time</>}.
        It is <b className="bad">confidently wrong on {model.confident_wrong}</b>
        {model.confident_wrong_high != null && <> ({model.confident_wrong_high} at high confidence)</>}. Hand it the
        public register and the only failure point left is <i>extraction</i> — which holds at{' '}
        <b className="good">{pct(tool.end_to_end_catch)}</b> through templated Methods-style sentences, every call cited to an ICLAC ID.
      </div>

      <div className="rp-stats">
        <div className="rp-stat model">
          <div className="rp-stat-num">{pct(model.strict_accuracy)}</div>
          <div className="rp-stat-cap">a frontier model names a contaminated line — from memory</div>
          <div className="rp-stat-sub">
            {flagRecall && <>flags it at all only {flagRecall} · </>}{model.confident_wrong} confident errors
            {model.confident_wrong_high != null && <> ({model.confident_wrong_high} high)</>} · 95% CI{' '}
            {pct(model.strict_ci[0])}–{pct(model.strict_ci[1])} (n={model.n_known})
          </div>
        </div>
        <div className="rp-stat tool">
          <div className="rp-stat-num">{pct(tool.end_to_end_catch)}</div>
          <div className="rp-stat-cap">the tool’s <b>catch rate</b> — reading the mix-up out of Methods-style sentences, end-to-end</div>
          <div className="rp-stat-sub">
            identity supplied by the register lookup, not the model · {ctrlFF} false alarms on {ctrlN} controls
            end-to-end · every FAIL cited
          </div>
        </div>
      </div>

      {realworld && (
        <div className="rp-realworld">
          <b>Tested on real papers, too.</b> Run over <b>{realworld.n_papers}</b> real open-access Methods
          sections (Europe PMC), the same engine extracted ~<b>{realworld.mean_resources}</b> resources per
          paper and caught <b className="good">{realworld.caught} of {realworld.verifiable}</b> register-listed
          contaminated lines named in those Methods, with <b className="good">{realworld.false_flags} false
          alarms</b> on <b>{realworld.clean_papers}</b> clean controls — <b className="good">specificity holds
          in the wild, and the real-world catch essentially matches the controlled 92%.</b>
        </div>
      )}

      <details className="rp-why">
        <summary>Why it exists — the two measurements behind these numbers</summary>
        <div className="rp-why-body">
          <div
            className="rp-bench-note"
            style={{ fontSize: 13, color: 'var(--text-muted, #8a8a8a)', margin: '2px 0 14px', lineHeight: 1.6 }}
          >
            <b>Two different measurements — not a head-to-head.</b> The model must recall the true identity from memory
            (strict, n={model.n_known}); the tool only has to extract the name from prose and look it up (n={tool.stress_n},
            95% CI {pct(tool.stress_ci[0])}–{pct(tool.stress_ci[1])}), so on a catch the identity is the register’s, not the
            model’s.{flagRecall && <> On the <i>same</i> question — did you flag a contaminated line at all? — the model manages{' '}
            {flagRecall} across all {model.n_misidentified} register lines to the tool’s {pct(tool.end_to_end_catch)} across a {tool.stress_n}-sentence
            stress corpus.</>} Measured across all {model.n_misidentified} misidentified lines, no cherry-picking: the model aces the ~11 famous cases ({pct(model.famous_acc)}) and collapses on
            the 519 obscure ones ({pct(model.tail_acc)}) — exactly where a researcher can’t eyeball it.
          </div>

          <div className="section-label">confidently wrong, where it matters — the model’s own words vs. the register</div>
          <div className="rp-cw-list">
            {examples.map((r) => (
              <div className="rp-cw" key={r.name}>
                <span className="rp-cw-name">{r.name}</span>
                <span className="rp-cw-model">
                  model says <em>{r.model_says}</em>
                  <span className="rp-cw-conf">{r.confidence}</span>
                </span>
                <span className="rp-cw-arrow">→</span>
                <span className="rp-cw-truth">
                  register says <strong>{r.register_says}</strong>
                </span>
                <span className="rp-cw-cite">{r.iclac_id} · {r.cvcl}</span>
              </div>
            ))}
          </div>
        </div>
      </details>
    </div>
  )
}

// Group findings by kind for display; anything outside the known kinds falls into "Other checks".
function groupFindings(report: ReproReport) {
  const groups = KIND_GROUPS
    .map((g) => ({ ...g, items: report.findings.filter((f) => f.kind === g.kind) }))
    .filter((g) => g.items.length > 0)
  const other = report.findings.filter((f) => !KIND_GROUPS.some((g) => g.kind === f.kind))
  return { groups, other }
}

// The rolled-up report card (verdict head + grouped findings). Reused by the single-paragraph verifier
// and the whole-manuscript review; per-finding Investigate is optional (off for the manuscript view).
function MethodsReport({ report, onInvestigate, canInvestigate, invState }: {
  report: ReproReport
  onInvestigate?: (f: ReproFinding) => void
  canInvestigate?: (f: ReproFinding) => boolean
  invState?: Record<string, { busy?: boolean; inv?: Investigation; error?: string }>
}) {
  const { groups, other } = groupFindings(report)
  const handler = (f: ReproFinding) => (onInvestigate && (!canInvestigate || canInvestigate(f))) ? onInvestigate : undefined
  const st = (f: ReproFinding) => invState?.[f.item]
  const rows = (items: ReproFinding[]) => items.map((f, i) => (
    <FindingRow key={f.item + i} f={f} onInvestigate={handler(f)} inv={st(f)?.inv} busy={st(f)?.busy} invError={st(f)?.error} />
  ))
  return (
    <div className="panel rp-report">
      <div className="rp-verdict-head">
        <span className={reproBadgeClass(report.verdict)}>{report.verdict}</span>
        <span className="rp-counts">
          <b className="fail">{report.n_fail}</b> to fix
          <span className="rp-dot">·</span>
          <b className="insuf">{report.n_insufficient}</b> to verify
          <span className="rp-dot">·</span>
          <b className="pass">{report.n_pass}</b> ok
        </span>
      </div>
      <div className="rp-legend">
        Every check is tagged <span className="rp-tag rule">registry</span> = looked up in a public
        database, a fixed rule decides · <span className="rp-tag model">model judgment</span> = Claude's
        reasoning. You always see which made the call.
      </div>
      {groups.map((g) => (
        <div className="rp-group" key={g.kind}>
          <div className="section-label">{g.label}</div>
          {rows(g.items)}
        </div>
      ))}
      {other.length > 0 && (
        <div className="rp-group">
          <div className="section-label">Other checks</div>
          {rows(other)}
        </div>
      )}
      <div className="rp-rail">
        A ✓ means <em>the cell line isn't on the mix-up register, or the reagent resolves to a public ID</em> —
        not proof of correctness. Absence from the register isn't proof of identity; confirm with a
        DNA-fingerprint (STR) test.
      </div>
    </div>
  )
}

// Phase 2 auto-fix: Claude-drafted, submission-ready corrections for the flagged findings. Each is a
// DRAFT grounded in the gate's own citation — it never invents an identity, and says so.
function Corrections({ items }: { items: Correction[] }) {
  if (!items.length) return null
  return (
    <div className="rp-group">
      <div className="section-label">Suggested corrections — drafts to paste back (human review required)</div>
      {items.map((c, i) => (
        <div key={c.item + i} style={{ margin: '8px 0', paddingLeft: 10, borderLeft: '2px solid var(--border,#333)' }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {c.item}
            <span className="rp-tag model" style={{ marginLeft: 8, fontSize: 11 }}>{c.label || 'draft — human review required'}</span>
          </div>
          {c.original && (
            <div style={{ fontSize: 12.5, color: 'var(--text-muted,#8a8a8a)', margin: '3px 0' }}><s>{c.original}</s></div>
          )}
          <div style={{ fontSize: 13, margin: '3px 0', lineHeight: 1.5 }}>{c.suggestion}</div>
          {c.rationale && <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8a8a)' }}>{c.rationale}</div>}
        </div>
      ))}
    </div>
  )
}

// Pre-filled full-Methods example for the whole-manuscript review mode (the frozen review_demo.json is
// the saved result for exactly this text, so the static build shows the beat with no backend).
const DEMO_MANUSCRIPT = `Cell culture. Experiments used the GR-M pancreatic carcinoma line and the SNB-19 glioblastoma line, maintained in DMEM supplemented with 10% FBS at 37C in 5% CO2.

Immunohistochemistry. Sections were stained with anti-Iba1 (FUJIFILM Wako, 019-19741; 1:500) to label microglia and with anti-GFAP (Dako) for astrocytes. Iba1 antibody specificity was confirmed in Iba1-knockout tissue, which showed no immunoreactivity.

Animals and analysis. Mice bearing orthotopic tumors were imaged weekly and survival was compared between groups by the log-rank test. Images were quantified in ImageJ (RRID:SCR_003070), flow-cytometry data were gated in FlowJo, and statistics were computed in GraphPad Prism (RRID:SCR_002798).`

export default function Repro() {
  const [bench, setBench] = useState<IclacBench | null>(null)
  const [report, setReport] = useState<ReproReport | null>(null)
  const [methods, setMethods] = useState('')
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [apiUp, setApiUp] = useState<boolean | null>(null)  // null = unknown; false = static host, no backend
  const abortRef = useRef<AbortController | null>(null)
  const [frozenInv, setFrozenInv] = useState<Record<string, Investigation>>({})
  const [invState, setInvState] = useState<Record<string, { busy?: boolean; inv?: Investigation; error?: string }>>({})
  // Phase 2: whole-manuscript review + draft auto-fix — a second mode of the same verifier.
  const [reviewMode, setReviewMode] = useState<'paragraph' | 'manuscript'>('paragraph')
  const [manuscript, setManuscript] = useState<ManuscriptReport | null>(null)
  const [manuscriptText, setManuscriptText] = useState(DEMO_MANUSCRIPT)
  const [mstate, setMstate] = useState<'idle' | 'loading' | 'error'>('idle')
  const [merror, setMerror] = useState<string | null>(null)

  // On mount: load the hero benchmark and the frozen demo report. Both are instant and
  // bulletproof — the frozen demo is what gets shown, and pre-fills the textarea.
  useEffect(() => {
    fetch('/repro/benchmark.json')
      .then((r) => r.json())
      .then((d: IclacBench) => setBench(d))
      .catch(() => {})
    fetch('/repro/demo.json')
      .then((r) => r.json())
      .then((d: ReproDeck) => {
        setReport(d.report)
        setMethods((cur) => cur || d.methods)
      })
      .catch(() => setError('Could not load the saved demo.'))
    // frozen agentic-investigation examples, so the static build can show the trail with no backend
    fetch('/repro/investigate_demo.json')
      .then((r) => r.json())
      .then((d: Record<string, Investigation>) => setFrozenInv(d))
      .catch(() => {})
    // frozen whole-manuscript review (report + drafted corrections), so the static build shows Phase 2
    fetch('/repro/review_demo.json')
      .then((r) => r.json())
      .then((d: ManuscriptReport) => setManuscript(d))
      .catch(() => {})
    // is a live backend reachable? (a static deploy has none — so we tell the judge upfront)
    fetch(api('/api/health'))
      .then((r) => setApiUp(r.ok))
      .catch(() => setApiUp(false))
  }, [])

  // Live verify: POST the Methods text to /api/repro with a client timeout. On success swap in
  // the live report; on error OR timeout, keep the frozen demo showing (never blank the view).
  const verify = () => {
    const m = methods.trim()
    if (m.length < 3 || state === 'loading') return
    const ctrl = new AbortController()
    abortRef.current = ctrl
    const timer = setTimeout(() => ctrl.abort(), LIVE_TIMEOUT_MS)
    setState('loading')
    setError(null)
    fetch(api('/api/repro'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ methods: m }),
      signal: ctrl.signal,
    })
      .then((r) => {
        if (!r.ok) throw new Error(`server returned ${r.status}`)
        return r.json()
      })
      .then((d: ReproDeck) => {
        if (d && d.report) setReport(d.report)
        setState('idle')
      })
      .catch((e) => {
        setError(
          e?.name === 'AbortError'
            ? 'Verification timed out — the saved example below still works.'
            : 'Verification failed (is the API running on :8010?). The saved example below still works.',
        )
        setState('error')
      })
      .finally(() => clearTimeout(timer))
  }

  // Launch the agentic investigator for one finding: live via /api/investigate, falling back to a
  // frozen saved investigation (keyed by the finding item) on a static host or any error.
  const runInvestigate = (f: ReproFinding) => {
    const key = f.item
    setInvState((s) => ({ ...s, [key]: { busy: true } }))
    // Bound the live agentic call: the loop hits PubMed/Cellosaurus and can run 10–90s. Abort past a
    // ceiling and fall back to the frozen saved investigation (a real captured result) so the view is
    // never stuck on a spinner — the same graceful-degradation discipline as verify().
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 16000)
    fetch(api('/api/investigate'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildInvReq(f)),
      signal: ctrl.signal,
    })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status))
        return r.json()
      })
      .then((d: { investigation: Investigation }) => setInvState((s) => ({ ...s, [key]: { inv: d.investigation } })))
      .catch(() => {
        const fz = frozenInv[key]
        setInvState((s) => ({
          ...s,
          [key]: fz
            ? { inv: fz }
            : { error: 'Live investigation needs the API (see README). This hosted build shows a saved example only where one was pre-captured.' },
        }))
      })
      .finally(() => clearTimeout(timer))
  }

  // Whole-manuscript review: POST the full text to /api/review (autofix on), same graceful fallback as
  // verify() — on error OR timeout keep the frozen review showing, never blank the view.
  const reviewManuscript = () => {
    const m = manuscriptText.trim()
    if (m.length < 20 || mstate === 'loading') return
    setMstate('loading')
    setMerror(null)
    fetch(api('/api/review'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ manuscript: m, autofix: true }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status))
        return r.json()
      })
      .then((d: { report: ManuscriptReport }) => {
        if (d && d.report) setManuscript(d.report)
        setMstate('idle')
      })
      .catch(() => {
        setMerror('Manuscript review needs the API (see README). The saved example below still works.')
        setMstate('error')
      })
  }

  // Offer "Investigate" only where it will actually resolve. A live backend can investigate any
  // cell line / antibody; a static host (no backend, apiUp === false) can only replay a pre-captured
  // frozen investigation — so on a static build we show the button ONLY for findings that have one,
  // never a button that would just error.
  const canInvestigate = (f: ReproFinding) =>
    (f.kind === 'cell_line' || f.kind === 'antibody') && (apiUp !== false || !!frozenInv[f.item])

  return (
    <div className="repro">
      <div className="tm-sub">
        Before you submit a paper, paste its Methods — the “how we did it” section. This flags cell lines that
        are secretly the wrong ones and reagents that can’t be traced, each linked to the public record that
        proves it — <b>before a journal reviewer does.</b>
      </div>

      {bench && <BenchmarkPanel bench={bench} />}

      <div className="modeswitch" style={{ marginBottom: 12 }}>
        <button type="button" className={'tab' + (reviewMode === 'paragraph' ? ' active' : '')}
          onClick={() => setReviewMode('paragraph')}>Verify a paragraph</button>
        <button type="button" className={'tab' + (reviewMode === 'manuscript' ? ' active' : '')}
          onClick={() => setReviewMode('manuscript')}>Review full manuscript + draft fixes</button>
      </div>

      {reviewMode === 'paragraph' && (<>
        <div className="tm-input rp-input">
          <textarea
            className="tm-note"
            value={methods}
            onChange={(e) => setMethods(e.target.value)}
            placeholder="Paste a Methods section. It checks each cell line, antibody, and software tool against public databases, and flags missing study-quality details (sample size, blinding, animal sex)."
            rows={5}
            disabled={state === 'loading'}
            aria-label="Methods section"
          />
          <div className="tm-actions">
            <button
              type="button"
              className={'tm-run' + (state === 'loading' ? ' busy' : '')}
              onClick={verify}
              disabled={methods.trim().length < 3 || state === 'loading' || apiUp === false}
            >
              {state === 'loading' ? (<><span className="lc-spin" /> verifying…</>) : 'Verify'}
            </button>
            <span className="tm-caption">
              {apiUp === false
                ? 'This hosted build shows saved examples. For live "Verify", clone the repo and run the API (see README).'
                : 'Verification runs one Claude extraction + deterministic registry lookups — a few seconds. The example below is a saved run.'}
            </span>
          </div>
          {error && <div className="tm-error">⚠ {error}</div>}
        </div>

        {report ? (
          <MethodsReport report={report} onInvestigate={runInvestigate} canInvestigate={canInvestigate} invState={invState} />
        ) : (
          !error && <div className="tm-loading"><span className="lc-spin" /> loading saved example…</div>
        )}
      </>)}

      {reviewMode === 'manuscript' && (<>
        <div className="tm-input rp-input">
          <textarea
            className="tm-note"
            value={manuscriptText}
            onChange={(e) => setManuscriptText(e.target.value)}
            placeholder="Paste a whole Methods / manuscript — every cell line, antibody, software tool, and study-quality item is checked, then Claude drafts the corrections."
            rows={9}
            disabled={mstate === 'loading'}
            aria-label="Manuscript text"
          />
          <div className="tm-actions">
            <button
              type="button"
              className={'tm-run' + (mstate === 'loading' ? ' busy' : '')}
              onClick={reviewManuscript}
              disabled={manuscriptText.trim().length < 20 || mstate === 'loading' || apiUp === false}
            >
              {mstate === 'loading' ? (<><span className="lc-spin" /> reviewing…</>) : 'Review manuscript + draft fixes'}
            </button>
            <span className="tm-caption">
              {apiUp === false
                ? 'This hosted build shows a saved manuscript review. For a live run, clone the repo and run the API (see README).'
                : 'Extracts every resource across the manuscript, runs all gates, then Claude drafts submission-ready corrections — a few seconds.'}
            </span>
          </div>
          {merror && <div className="tm-error">⚠ {merror}</div>}
        </div>

        {manuscript ? (<>
          <div className="rp-rail" style={{ marginTop: 0 }}>
            Reviewed <b>{manuscript.n_resources}</b> resource{manuscript.n_resources === 1 ? '' : 's'} across{' '}
            <b>{manuscript.n_chunks}</b> chunk{manuscript.n_chunks === 1 ? '' : 's'} · every correction is a labelled draft.
          </div>
          <MethodsReport report={manuscript.report} />
          <Corrections items={manuscript.corrections} />
        </>) : (
          !merror && <div className="tm-loading"><span className="lc-spin" /> loading saved example…</div>
        )}
      </>)}

      <div className="disclaimer">
        <b>Research and pre-submission screening aid</b> — not a substitute for STR authentication or peer review. The
        tool's edge is the obscure long tail and citability, not the famous cases a model already knows.
      </div>
    </div>
  )
}
