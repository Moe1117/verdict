export type VerdictState = 'Supported' | 'Not Supported' | 'Contested' | 'Insufficient'

export interface GateStep {
  gate: string
  passed: boolean
  detail: string
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
  baseline?: Baseline | null
  gate_trace: GateStep[]
  ledger: EvidenceRow[]
  disclaimer: string
}
