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
export type ReproKind = 'cell_line' | 'antibody' | 'knockout' | 'software' | 'rigor'
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
  // e.g. "ICLAC-00538 · CVCL_2451" or "RRID:AB_2665520" (may be empty).
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

// ── Agentic Investigator: Claude autonomously searches PubMed/Cellosaurus for real-citation evidence ──

export interface InvestigationCitation {
  id: string          // "PMID:30679523" | "CVCL_2451" | "RRID:AB_..."
  kind: string        // "pubmed" | "cellosaurus" | "antibody_registry"
  title?: string
  why?: string
}

export interface Investigation {
  kind: string        // "antibody" | "cell_line"
  verdict: string     // FOUND_VALIDATION | NO_VALIDATION_FOUND | PROVENANCE_CHAIN | PARTIAL | INCONCLUSIVE
  cited: InvestigationCitation[]
  reasoning: string
  steps: string[]     // the agentic trail (searched -> read -> concluded)
  grounded: boolean
  method: string
}

// ── Phase 2: whole-manuscript review + draft auto-fix (POST /api/review) ──

export interface Correction {
  item: string        // which finding this fixes, e.g. "cell line: GR-M"
  original: string    // the verbatim manuscript phrase being corrected ("" if none)
  suggestion: string  // the drafted corrective text
  rationale: string   // why (traces to the gate's deterministic citation)
  label: string       // "draft — human review required"
}

export interface ManuscriptReport {
  report: ReproReport
  investigations: Investigation[]
  corrections: Correction[]
  n_resources: number
  n_chunks: number
}

// POST /api/review returns { report: ManuscriptReport }.
export interface ManuscriptDeck {
  report: ManuscriptReport
}

export interface IclacBenchExample {
  name: string
  model_says: string
  confidence: 'high' | 'medium' | 'low' | string
  register_says: string
  iclac_id: string
  cvcl: string
}

export interface IclacBench {
  model: {
    strict_accuracy: number
    strict_ci: [number, number]
    flag_recall?: number          // same-task honest comparison: did it flag the line at all?
    confident_wrong: number
    confident_wrong_high?: number // of the confident-wrong, how many at HIGH confidence
    n_misidentified: number
    n_known: number
    famous_acc: number
    tail_acc: number
  }
  tool: {
    end_to_end_catch: number
    stress_n: number
    stress_ci: [number, number]
    false_flags: number           // register-lookup specificity (bare names, no extraction)
    n_controls: number
    false_flags_endtoend?: number // end-to-end specificity (through prose), measured separately
    n_controls_endtoend?: number
    match_misses: number
  }
  examples: IclacBenchExample[]
}
