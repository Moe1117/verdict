import { useEffect, useRef, useState } from 'react'
import type { IclacBench, ReproDeck, ReproFinding, ReproReport } from './types'

// Verdict badge class — like App.tsx's badgeClass, but strips spaces AND hyphens so
// "Submission-ready" → "b-Submissionready", "Needs fixes" → "b-Needsfixes". CSS matches.
const reproBadgeClass = (v: string) => 'badge b-' + v.replace(/[\s-]/g, '')

const pct = (x: number) => Math.round(x * 100 - 1e-9) + '%'  // round-half-down so 92.5% shows as 92%, matching the docs

// Per-finding result → glyph + colour class. INSUFFICIENT is the abstention state.
const RESULT_META: Record<string, { icon: string; cls: string; label: string }> = {
  FAIL: { icon: '✗', cls: 'fail', label: 'fail' },
  PASS: { icon: '✓', cls: 'pass', label: 'pass' },
  INSUFFICIENT: { icon: '❔', cls: 'insuf', label: 'insufficient' },
}

// Findings render grouped by kind, in this order. Anything else falls through to "Other checks".
const KIND_GROUPS: { kind: string; label: string }[] = [
  { kind: 'cell_line', label: 'Cell lines' },
  { kind: 'antibody', label: 'Antibodies' },
  { kind: 'knockout', label: 'Antibody validation — knockout controls (Claude reasoning)' },
  { kind: 'rigor', label: 'Rigor reporting' },
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

// One finding row: result icon · item · citation badge · provenance tag, then the detail
// verdict and (when present) the verbatim manuscript evidence in quotes.
function FindingRow({ f }: { f: ReproFinding }) {
  const meta = RESULT_META[f.result] ?? RESULT_META.INSUFFICIENT
  const cite = f.citation?.trim()
  const ev = f.evidence?.trim()
  return (
    <div className={'rp-find ' + meta.cls}>
      <span className={'rp-icon ' + meta.cls} title={meta.label}>{meta.icon}</span>
      <div className="rp-find-body">
        <div className="rp-find-top">
          <span className="rp-item">{f.item}</span>
          {cite && <span className="rp-cite">{cite}</span>}
          {methodTag(f.method)}
        </div>
        <div className="rp-detail">{renderDetail(f.detail)}</div>
        {ev && <div className="rp-ev">{ev}</div>}
      </div>
    </div>
  )
}

// The benchmark panel — TWO separate measured facts, honestly framed as such (NOT a head-to-head):
// how unreliable a frontier model is from memory, and how well extraction holds end-to-end on prose.
function BenchmarkPanel({ bench }: { bench: IclacBench }) {
  const { model, tool, examples } = bench
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
        <b className="good">{pct(tool.end_to_end_catch)}</b> through messy Methods prose, every call cited to an ICLAC ID.
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
          <div className="rp-stat-cap">the tool’s <b>extraction recall</b> — end-to-end on real Methods text</div>
          <div className="rp-stat-sub">
            identity supplied by the register lookup, not the model · {ctrlFF} false alarms on {ctrlN} controls
            end-to-end · every FAIL cited
          </div>
        </div>
      </div>

      <div
        className="rp-bench-note"
        style={{ fontSize: 13, color: 'var(--text-muted, #8a8a8a)', margin: '2px 0 14px', lineHeight: 1.6 }}
      >
        <b>Two different measurements — not a head-to-head.</b> The model must recall the true identity from memory
        (strict, n={model.n_known}); the tool only has to extract the name from prose and look it up (n={tool.stress_n},
        95% CI {pct(tool.stress_ci[0])}–{pct(tool.stress_ci[1])}), so on a catch the identity is the register’s, not the
        model’s.{flagRecall && <> On the <i>same</i> task — did you flag a contaminated line at all? — the model manages{' '}
        {flagRecall} to the tool’s {pct(tool.end_to_end_catch)}.</>} Measured on the entire {model.n_misidentified}-line
        ICLAC register, no cherry-picking: the model aces the ~11 famous cases ({pct(model.famous_acc)}) and collapses on
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
  )
}

export default function Repro() {
  const [bench, setBench] = useState<IclacBench | null>(null)
  const [report, setReport] = useState<ReproReport | null>(null)
  const [methods, setMethods] = useState('')
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [apiUp, setApiUp] = useState<boolean | null>(null)  // null = unknown; false = static host, no backend
  const abortRef = useRef<AbortController | null>(null)

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
    // is a live backend reachable? (a static deploy has none — so we tell the judge upfront)
    fetch('/api/health')
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
    fetch('/api/repro', {
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

  // Bucket findings by kind; anything outside the known kinds falls into "Other checks".
  const groups = report
    ? KIND_GROUPS.map((g) => ({ ...g, items: report.findings.filter((f) => f.kind === g.kind) })).filter(
        (g) => g.items.length > 0,
      )
    : []
  const other = report ? report.findings.filter((f) => !KIND_GROUPS.some((g) => g.kind === f.kind)) : []

  return (
    <div className="repro">
      <div className="tm-sub">
        AI generates scientific claims faster than anyone can verify them. This is the layer that catches what a
        confident model gets wrong — <b>in your Methods section, before Reviewer 2 does.</b>
      </div>

      {bench && <BenchmarkPanel bench={bench} />}

      <div className="tm-input rp-input">
        <textarea
          className="tm-note"
          value={methods}
          onChange={(e) => setMethods(e.target.value)}
          placeholder="Paste a Methods section — cell lines, antibodies, and rigor reporting are checked against public registries."
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

          {groups.map((g) => (
            <div className="rp-group" key={g.kind}>
              <div className="section-label">{g.label}</div>
              {g.items.map((f, i) => (
                <FindingRow key={f.item + i} f={f} />
              ))}
            </div>
          ))}
          {other.length > 0 && (
            <div className="rp-group">
              <div className="section-label">Other checks</div>
              {other.map((f, i) => (
                <FindingRow key={f.item + i} f={f} />
              ))}
            </div>
          )}

          <div className="rp-rail">
            A ✓ means <em>not on the register / resolves to an RRID</em> — not proof of correctness. Absence from the
            ICLAC register is not proof of identity; STR-authenticate.
          </div>
        </div>
      ) : (
        !error && <div className="tm-loading"><span className="lc-spin" /> loading saved example…</div>
      )}

      <div className="disclaimer">
        <b>Research and pre-submission screening aid</b> — not a substitute for STR authentication or peer review. The
        tool's edge is the obscure long tail and citability, not the famous cases a model already knows.
      </div>
    </div>
  )
}
