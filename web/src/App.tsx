import { useEffect, useState } from 'react'
import type { Card, EvidenceRow } from './types'

// Canned "plain LLM" answers — deliberately confident, to contrast with Verdict.
const BASELINES: Record<string, string> = {
  C08: 'Yes — several studies and a meta-analysis reported reduced mortality (RR ~0.31), so ivermectin appears beneficial for COVID-19.',
  C09: 'Fenbendazole has shown anti-cancer activity in studies and may help treat cancer.',
  C01: 'Yes — atorvastatin reliably lowers LDL cholesterol in adults with high cholesterol.',
  C05: 'Yes — metformin use is associated with lower cancer incidence across many studies.',
  C14: 'Yes — omega-3 (icosapent ethyl) reduces cardiovascular events, as shown in REDUCE-IT.',
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
  const [id, setId] = useState<string>('C08')
  const [runKey, setRunKey] = useState(0)

  useEffect(() => {
    fetch('/cards.json')
      .then((r) => r.json())
      .then((cs: Card[]) => setCards(cs))
  }, [])

  const select = (cid: string) => { setId(cid); setRunKey((k) => k + 1) }
  const card = cards.find((c) => c.id === id)

  return (
    <div className="wrap">
      <div className="head">
        <div className="logo">Verdict<span className="dot">.</span></div>
        <div className="tag">Grades the evidence. Knows when to abstain.</div>
      </div>
      <div className="sub">
        Paste a biomedical efficacy claim. Claude extracts the evidence; a deterministic engine — with no LLM in the
        verdict path — makes the call, so every verdict is auditable to its source. When the evidence can’t decide, Verdict abstains.
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

      {card && (
        <div className="disclaimer">
          <b>Verdict grades the state of published evidence.</b> It is a research and literature-triage tool for
          professionals — not medical advice, not a diagnosis, not a treatment recommendation.
        </div>
      )}
    </div>
  )
}
