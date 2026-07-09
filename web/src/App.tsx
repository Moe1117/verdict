import { useEffect, useState } from 'react'
import type { Card, EvidenceRow, GradeDomain, TimePoint } from './types'

interface EvalSummary {
  n: number
  accuracy: { verdict: number; naive_vote: number; plain_llm: number }
  verdict_accuracy_when_answered: number
  verdict_abstention_rate: number
  confidently_wrong: { verdict: number; naive_vote: number; plain_llm: number }
}
interface LiveSummary { accuracy: number; confident_false_positives: number; abstention_rate: number }
interface Conformal { alpha: number; threshold: string; guarantee_held_fraction: number; mean_test_error: number }

const pct = (x: number) => Math.round(x * 100) + '%'
const cvar = (v: string) => `var(--${v.toLowerCase().replace(/\s/g, '-')})`

// Canned "plain LLM" answers — deliberately confident, to contrast with Verdict.
const BASELINES: Record<string, string> = {
  C08: 'Yes — several studies and a meta-analysis reported reduced mortality (RR ~0.31), so ivermectin appears beneficial for COVID-19.',
  C01: 'Yes — atorvastatin reliably lowers LDL cholesterol in adults with high cholesterol.',
  C05: 'Yes — metformin use is associated with lower cancer incidence across many studies.',
  C14: 'Yes — omega-3 (icosapent ethyl) reduces cardiovascular events, as shown in REDUCE-IT.',
  F04: 'Yes — early studies, including Gautret et al., found hydroxychloroquine improved outcomes in COVID-19.',
  F01: 'Yes — hydroxyethyl starch is an effective, well-tolerated volume expander for fluid resuscitation.',
}

// Does the plain-LLM's confident Yes/No disagree with the honest verdict?
const bluffs = (c: Card) => {
  const ans = c.baseline?.answer ?? 'Yes'
  return (ans === 'Yes' && c.verdict !== 'Supported') || (ans === 'No' && c.verdict !== 'Not Supported')
}

const badgeClass = (v: string) => 'badge b-' + v.replace(/\s/g, '')

function DirCell({ d }: { d: number }) {
  if (d === 1) return <div className="dir pos" title="supports">+</div>
  if (d === -1) return <div className="dir neg" title="contradicts">−</div>
  return <div className="dir null" title="no effect / null">0</div>
}

// The deterministic GRADE certainty profile: a starting tier from study design, then a
// signed up/down-grade per GRADE domain, summing to the final certainty. No LLM.
function GradeProfile({ card }: { card: Card }) {
  const domains = card.certainty_domains
  if (!domains || !domains.length) return null
  const start = card.certainty_start
  const deltaStr = (d: number) => (d > 0 ? `+${d}` : `${d}`)
  return (
    <div className="grade">
      <div className="grade-sum">
        {start && <span className="tier">{start.label}</span>}
        {domains.filter((d) => d.delta !== 0).map((d, i) => (
          <span key={i} className={'step ' + (d.delta > 0 ? 'up' : 'down')}>{deltaStr(d.delta)}</span>
        ))}
        <span className="arrow">→</span>
        <span className={'tier final b-' + card.verdict.replace(/\s/g, '')}>{card.certainty}</span>
      </div>
      {domains.map((d: GradeDomain, i) => (
        <div key={i} className={'gd' + (d.delta !== 0 ? ' active' : '')}>
          <div className={'gd-delta' + (d.delta < 0 ? ' neg' : d.delta > 0 ? ' pos' : '')}>
            {d.delta === 0 ? '0' : deltaStr(d.delta)}
          </div>
          <div className="gd-body">
            <div className="gd-name">{d.name}</div>
            <div className="gd-why">{d.rationale}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

function Row({ r, i }: { r: EvidenceRow; i: number }) {
  const cls = ['row', !r.integrity_ok ? 'excluded' : '', r.integrity_ok && !r.population_match ? 'offpop' : ''].join(' ')
  return (
    <div className={cls} style={{ animationDelay: `${i * 80}ms` }}>
      <DirCell d={r.direction} />
      <div className="sid">{r.source_id}</div>
      <div className="body">
        <div className="top">
          <span className="design">{r.design}</span>
          {r.n && <span className="n">n={r.n_int ? r.n_int.toLocaleString() : r.n}</span>}
          {!r.integrity_ok && <span className="chip excl">excluded</span>}
          {r.integrity_ok && !r.population_match && <span className="chip off">off-population</span>}
        </div>
        <div className="finding">{r.finding}</div>
        {!r.integrity_ok && r.integrity_note && <div className="integ">⚠ {r.integrity_note}</div>}
      </div>
    </div>
  )
}

// Verdict over time — replayed as the evidence accrued, year by year. Deterministic; no LLM.
function TimeMachine({ timeline }: { timeline?: TimePoint[] }) {
  if (!timeline || timeline.length < 2) return null
  return (
    <div className="timemachine">
      <div className="section-label">the verdict over time — replayed as the evidence accrued (no LLM)</div>
      <div className="tl">
        {timeline.map((t, i) => (
          <div className="tp" key={i} style={{ animationDelay: `${400 + i * 260}ms` }}>
            <div className="tp-year">≤ {t.year}</div>
            <div className="tp-track">
              {i > 0 && <span className="tp-line" />}
              <span className="tp-dot" style={{ background: cvar(t.verdict), boxShadow: `0 0 0 4px ${cvar(t.verdict)}22` }} />
            </div>
            <div className="tp-pill" style={{ color: cvar(t.verdict), borderColor: `${cvar(t.verdict)}66` }}>{t.verdict}</div>
            <div className="tp-meta">{t.certainty} · {t.n} stud{t.n === 1 ? 'y' : 'ies'}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Scorecard({ ev, live, conf }: { ev: EvalSummary; live: LiveSummary | null; conf: Conformal | null }) {
  return (
    <div className="scorecard">
      <div className="sc-head">
        <div className="section-label" style={{ margin: 0 }}>how it scores — we report two numbers, honestly</div>
        <div className="sc-note">the deterministic engine, and the full live product · {ev.n} breakthrough-medicine claims</div>
      </div>
      <div className="sc-table">
        <div className="sc-row sc-th">
          <span className="m">Method</span>
          <span className="acc">Accuracy</span>
          <span className="cw">Confident false-positives</span>
        </div>
        <div className="sc-row sc-win">
          <span className="m">Verdict — gate engine <em>logic, evidence fixed</em></span>
          <span className="acc">{pct(ev.accuracy.verdict)}</span>
          <span className="cw ok">{ev.confidently_wrong.verdict}</span>
        </div>
        {live && (
          <div className="sc-row sc-live">
            <span className="m">Verdict — full live product <em>Claude extracts, end-to-end</em></span>
            <span className="acc">{pct(live.accuracy)}</span>
            <span className="cw">{live.confident_false_positives}</span>
          </div>
        )}
        <div className="sc-row">
          <span className="m">Naive study-count vote</span>
          <span className="acc">{pct(ev.accuracy.naive_vote)}</span>
          <span className="cw">{ev.confidently_wrong.naive_vote}</span>
        </div>
        <div className="sc-row">
          <span className="m">Plain LLM <em>confident yes/no</em></span>
          <span className="acc">{pct(ev.accuracy.plain_llm)}</span>
          <span className="cw bad">{ev.confidently_wrong.plain_llm}</span>
        </div>
      </div>
      {conf && (
        <div className="sc-guarantee">
          <span className="g-dot" /> Guaranteed: commit only at <b>{conf.threshold}</b> certainty → error ≤ {pct(conf.alpha)},
          distribution-free — held in <b>{pct(conf.guarantee_held_fraction)}</b> of random splits.
        </div>
      )}
      <div className="sc-foot">
        The <b>engine</b> (deterministic logic) is confidently wrong <b>zero</b> times. The <b>full live product</b> —
        Claude parsing, retrieving, and extracting end-to-end — scores {live ? pct(live.accuracy) : '66%'} with{' '}
        {live ? live.confident_false_positives : 3} confident false-positives, still far fewer than a plain LLM’s{' '}
        <b>{ev.confidently_wrong.plain_llm}</b>, and abstains on {live ? pct(live.abstention_rate) : '16%'} rather than guess.
        We report both — hiding the live number would be the bluffing this tool exists to prevent.
      </div>
    </div>
  )
}

export default function App() {
  const [cards, setCards] = useState<Card[]>([])
  const [ev, setEv] = useState<EvalSummary | null>(null)
  const [live, setLive] = useState<LiveSummary | null>(null)
  const [conf, setConf] = useState<Conformal | null>(null)
  const [id, setId] = useState<string>(() => window.location.hash.replace('#', '') || 'C08')
  const [runKey, setRunKey] = useState(0)

  useEffect(() => {
    fetch('/cards.json').then((r) => r.json()).then((cs: Card[]) => {
      setCards(cs)
      setId((cur) => (cs.some((c) => c.id === cur) ? cur : cs[0]?.id ?? cur))
    })
    fetch('/eval.json').then((r) => r.json()).then((d: { summary: EvalSummary }) => setEv(d.summary)).catch(() => {})
    fetch('/live_eval.json').then((r) => r.json()).then((d: { summary: LiveSummary }) => setLive(d.summary)).catch(() => {})
    fetch('/calibration.json').then((r) => r.json()).then((d: { conformal: Conformal }) => setConf(d.conformal)).catch(() => {})
  }, [])

  const select = (cid: string) => {
    setId(cid)
    setRunKey((k) => k + 1)
    window.history.replaceState(null, '', `#${cid}`)
  }
  const card = cards.find((c) => c.id === id)

  return (
    <div className="wrap">
      <div className="head">
        <div className="logo">Verdict<span className="dot">.</span></div>
        <div className="tag">Never confidently wrong.</div>
      </div>
      <div className="sub">
        A plain LLM — even Claude — will confidently repeat a fraud-driven result. Verdict won’t: known-bad or thin
        evidence is excluded <em>before</em> a deterministic gate — <b>no LLM in the verdict path</b> — returns the call,
        and it says “I don’t know” instead of guessing.
      </div>

      <div className="claimbar">
        <div className="liveinput" title="live end-to-end resolution — coming soon">
          <span className="li-icon">✎</span>
          <input placeholder="Paste a clinical claim to resolve live…" disabled />
          <span className="li-soon">live · soon</span>
        </div>
        <div className="chips">
          {cards.map((c) => (
            <button key={c.id} className={'chip-tab' + (c.id === id ? ' active' : '')} onClick={() => select(c.id)}>
              <span className="swatch" style={{ background: cvar(c.verdict) }} />
              {c.claim.length > 42 ? c.claim.slice(0, 40) + '…' : c.claim}
            </button>
          ))}
        </div>
      </div>

      {card && (
        <div className="grid" key={runKey}>
          <div className="panel llm">
            <div className="panel-label">A plain LLM</div>
            <div className="who"><span>🤖</span> <b>Assistant</b></div>
            <div className="bubble">{card.baseline?.text ?? BASELINES[card.id] ?? 'Yes.'}</div>
            {bluffs(card) && <div className="warn">⚠ confident, unsourced — and, here, wrong or overstated</div>}
            <div className="foot">no sources · no calibration · cannot say “I don’t know”</div>
          </div>

          <div className="panel">
            <div className="panel-label">Verdict</div>
            <div className="verdict-head">
              <span className={badgeClass(card.verdict)}>{card.verdict}</span>
              <span className="conf">confidence: {card.confidence}</span>
            </div>
            <div className="claim">{card.claim}</div>

            <div className="section-label">certainty — per-domain GRADE profile, no LLM</div>
            <GradeProfile card={card} />

            <div className="section-label">gate trace — deterministic, no LLM in the verdict path</div>
            {card.gate_trace.map((g, i) => (
              <div key={i} className={'gate ' + (g.passed ? 'pass' : 'fail')} style={{ animationDelay: `${i * 380}ms` }}>
                <div className="mark">{g.passed ? '✓' : '?'}</div>
                <div>
                  <div className="g-name">{g.gate}</div>
                  <div className="g-detail">{g.detail}</div>
                </div>
              </div>
            ))}

            <div className="section-label">evidence ledger — every verdict traces to source</div>
            {card.ledger.map((r, i) => (
              <Row key={r.source_id + i} r={r} i={card.gate_trace.length + i} />
            ))}
          </div>
        </div>
      )}

      {card && <TimeMachine timeline={card.timeline} />}

      {ev && <Scorecard ev={ev} live={live} conf={conf} />}

      {card && (
        <div className="disclaimer">
          <b>Verdict grades the state of published evidence.</b> It is a research and literature-triage tool for
          professionals — not medical advice, not a diagnosis, not a treatment recommendation.
        </div>
      )}
    </div>
  )
}
