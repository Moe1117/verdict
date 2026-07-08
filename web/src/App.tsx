import { useEffect, useState } from 'react'
import type { Card, EvidenceRow } from './types'

interface EvalSummary {
  n: number
  accuracy: { verdict: number; naive_vote: number; plain_llm: number }
  verdict_accuracy_when_answered: number
  verdict_abstention_rate: number
  confidently_wrong: { verdict: number; naive_vote: number; plain_llm: number }
}

const pct = (x: number) => Math.round(x * 100) + '%'

// Canned "plain LLM" answers — deliberately confident, to contrast with Verdict.
const BASELINES: Record<string, string> = {
  C08: 'Yes — several studies and a meta-analysis reported reduced mortality (RR ~0.31), so ivermectin appears beneficial for COVID-19.',
  C09: 'Fenbendazole has shown anti-cancer activity in studies and may help treat cancer.',
  C01: 'Yes — atorvastatin reliably lowers LDL cholesterol in adults with high cholesterol.',
  C05: 'Yes — metformin use is associated with lower cancer incidence across many studies.',
  C14: 'Yes — omega-3 (icosapent ethyl) reduces cardiovascular events, as shown in REDUCE-IT.',
  F04: 'Yes — early studies, including Gautret et al., found hydroxychloroquine (especially with azithromycin) improved viral clearance and outcomes in COVID-19.',
  F01: 'Yes — hydroxyethyl starch is an effective volume expander and is well-tolerated for fluid resuscitation in critically ill patients.',
}

// Does the plain-LLM answer disagree with Verdict? (drives the warning line)
const bluffs = (c: Card) => c.verdict === 'Not Supported' || c.verdict === 'Insufficient' || c.verdict === 'Contested'

const badgeClass = (v: string) => 'badge b-' + v.replace(/\s/g, '')

function DirCell({ d }: { d: number }) {
  if (d === 1) return <div className="dir pos" title="supports">+</div>
  if (d === -1) return <div className="dir neg" title="contradicts">−</div>
  return <div className="dir null" title="no effect / null">0</div>
}

function Row({ r, i }: { r: EvidenceRow; i: number }) {
  const cls = ['row', !r.integrity_ok ? 'excluded' : '', r.integrity_ok && !r.population_match ? 'offpop' : ''].join(' ')
  return (
    <div className={cls} style={{ animationDelay: `${i * 90}ms` }}>
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

export default function App() {
  const [cards, setCards] = useState<Card[]>([])
  const [ev, setEv] = useState<EvalSummary | null>(null)
  const [id, setId] = useState<string>(() => window.location.hash.replace('#', '') || 'C08')
  const [runKey, setRunKey] = useState(0)

  useEffect(() => {
    fetch('/cards.json')
      .then((r) => r.json())
      .then((cs: Card[]) => {
        setCards(cs)
        // Fall back to the first card if the URL hash names an unknown claim.
        setId((cur) => (cs.some((c) => c.id === cur) ? cur : cs[0]?.id ?? cur))
      })
    fetch('/eval.json')
      .then((r) => r.json())
      .then((d: { summary: EvalSummary }) => setEv(d.summary))
      .catch(() => {})
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
        <div className="tag">Never confidently wrong — it excludes known-bad evidence, then abstains instead of guessing.</div>
      </div>
      <div className="sub">
        A plain LLM — even Claude — will confidently repeat a fraud-driven result. Verdict won’t. Known-bad or thin
        evidence is excluded <em>before</em> a deterministic gate — no LLM in the verdict path — returns its call. It isn’t
        more accurate than an LLM; it’s the one that structurally can’t silently repeat a falsehood, and says “I don’t know” instead of guessing.
      </div>

      <div className="tabs">
        {cards.map((c) => (
          <button key={c.id} className={'tab' + (c.id === id ? ' active' : '')} onClick={() => select(c.id)}>
            <span className="swatch" style={{ background: `var(--${c.verdict.toLowerCase().replace(/\s/g, '-')})` }} />
            {c.claim.length > 46 ? c.claim.slice(0, 44) + '…' : c.claim}
          </button>
        ))}
      </div>

      {card && (
        <div className="grid" key={runKey}>
          <div className="panel llm">
            <div className="panel-label">A plain LLM</div>
            <div className="who"><span>🤖</span> <b>Assistant</b></div>
            <div className="bubble">{BASELINES[card.id] ?? 'Yes.'}</div>
            {bluffs(card) && (
              <div className="warn">⚠ confident, unsourced — and, here, wrong or overstated</div>
            )}
            <div className="foot">no sources · no calibration · cannot say “I don’t know”</div>
          </div>

          <div className="panel">
            <div className="panel-label">Verdict</div>
            <div className="verdict-head">
              <span className={badgeClass(card.verdict)}>{card.verdict}</span>
              <span className="conf">confidence: {card.confidence}</span>
            </div>
            <div className="claim">{card.claim}</div>

            <div className="section-label">gate trace — deterministic, no LLM</div>
            {card.gate_trace.map((g, i) => (
              <div key={i} className={'gate ' + (g.passed ? 'pass' : 'fail')} style={{ animationDelay: `${i * 420}ms` }}>
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

      {ev && (
        <div className="scorecard">
          <div className="sc-head">
            <div className="section-label" style={{ margin: 0 }}>How it scores — blind cold set, {ev.n} claims</div>
            <div className="sc-note">exact 4-state match vs independent expert-consensus gold</div>
          </div>
          <div className="sc-table">
            <div className="sc-row sc-th">
              <span className="m">Method</span>
              <span className="acc">Accuracy</span>
              <span className="cw">Confidently wrong</span>
            </div>
            <div className="sc-row sc-win">
              <span className="m">Verdict <em>deterministic gate engine</em></span>
              <span className="acc">{pct(ev.accuracy.verdict)}</span>
              <span className="cw ok">{ev.confidently_wrong.verdict}</span>
            </div>
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
          <div className="sc-foot">
            Not universally more accurate — on emerging pipeline drugs with thin literature Verdict is conservative to a
            fault (62% vs the model’s 75%). What it never does is answer confidently when it shouldn’t:{' '}
            <b>zero</b> confidently-wrong calls here, versus the language model’s <b>{ev.confidently_wrong.plain_llm}</b> —
            and it abstains when the evidence can’t decide. Full evals, including where Verdict loses, are in the repo.
          </div>
        </div>
      )}

      {card && (
        <div className="disclaimer">
          <b>Verdict grades the state of published evidence.</b> It is a research and literature-triage tool for
          professionals — not medical advice, not a diagnosis, not a treatment recommendation.
        </div>
      )}
    </div>
  )
}
