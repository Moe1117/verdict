export type VerdictState = 'Supported' | 'Not Supported' | 'Contested' | 'Insufficient' | 'Undecidable'

export interface GateStep {
  gate: string
  passed: boolean
  detail: string
}

export interface GradeDomain {
  name: string
  delta: number
  rationale: string
}

export interface TimePoint {
  year: number
  verdict: string
  certainty: string
  n: number
  changed: boolean
}

export interface EvidenceRow {
  citation: string
  design: string
  direction: number
  population_match: boolean
  source_id: string
  integrity_ok: boolean
  n: string
  n_int: number
  year: number
  finding: string
  integrity_note: string
  note: string
}

export interface Baseline {
  answer: 'Yes' | 'No'
  confidence: string
  text: string
}

export interface Card {
  id: string
  claim: string
  verdict: VerdictState
  expected: string
  confidence: string
  certainty: string
  certainty_start?: { score: number; label: string }
  certainty_domains?: GradeDomain[]
  certainty_signals?: string[]
  timeline?: TimePoint[]
  baseline?: Baseline | null
  gate_trace: GateStep[]
  ledger: EvidenceRow[]
  what_would_change_it?: string
  disclaimer: string
}
