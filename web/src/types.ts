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
  dose_match?: boolean
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

// ── TrialMatch (Task 10): patient-note → ranked recruiting-trial eligibility ──

export type TrialVerdict = 'Likely eligible' | 'Ineligible' | 'Needs verification'
export type CriterionResult = 'MET' | 'NOT_MET' | 'INSUFFICIENT'

export interface TrialCriterion {
  id: string
  kind: 'inclusion' | 'exclusion'
  result: CriterionResult
  confidence?: string
  evidence_phrase?: string
  note?: string
  predicate: string
  source_text?: string
  // "structured" = deterministic rule; "semantic" = model judgment. May be absent — render no tag then.
  ctype?: 'structured' | 'semantic' | string
}

export interface TrialCard {
  nct_id: string
  title: string
  status: string
  url: string
  verdict: TrialVerdict
  criteria: TrialCriterion[]
  to_verify: string[]
  n_met: number
  n_disqualifying: number
  n_to_verify: number
}

export interface TrialDeck {
  note: string
  cards: TrialCard[]
}

// ── Repro (verification layer): Methods-section reproducibility screen ──

export type ReproResult = 'FAIL' | 'PASS' | 'INSUFFICIENT'
export type ReproKind = 'cell_line' | 'antibody' | 'rigor'
export type ReproVerdict = 'Submission-ready' | 'Needs fixes' | 'Needs verification'

export interface ReproFinding {
  item: string
  // "cell_line" | "antibody" | "rigor" — may be an unknown string; render under "Other checks" then.
  kind: ReproKind | string
  result: ReproResult
  // human-readable verdict; may contain **bold** markdown-ish markers.
  detail: string
  // verbatim phrase from the manuscript (may be empty).
  evidence: string
  // e.g. "ICLAC ICLAC-00538 · CVCL_2451" or "RRID:AB_2665520" (may be empty).
  citation: string
  // "rule" → registry lookup; "model judgment" → Claude. May be absent/unknown → no tag.
  method: 'rule' | 'model judgment' | string
}

export interface ReproReport {
  findings: ReproFinding[]
  verdict: ReproVerdict
  n_fail: number
  n_pass: number
  n_insufficient: number
  to_fix: string[]
}

export interface ReproDeck {
  methods: string
  report: ReproReport
}

export interface IclacBenchRow {
  name: string
  true_identity: string
  iclac_id: string
  cvcl: string
  llm_verdict: string
  llm_confidence: 'high' | 'medium' | 'low' | string
  llm_correct: boolean
  llm_confident_wrong: boolean
}

export interface IclacBench {
  summary: {
    n: number
    llm_accuracy: number
    llm_confident_wrong: number
    tool_accuracy: number
    tool_confident_wrong: number
  }
  rows: IclacBenchRow[]
}
