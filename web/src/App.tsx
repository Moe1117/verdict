import Repro from './Repro'

// Verdict is the Methods Verifier. The trial-eligibility reviewer (TrialMatch.tsx) and the
// evidence resolver were sibling prototypes on the way here — kept in git history, not the entry
// point. The product is one thing: catch what a confident model gets wrong in a Methods section.
export default function App() {
  return (
    <div className="wrap">
      <div className="head">
        <div className="logo">Verdict<span className="dot">.</span></div>
        <div className="tag">Catches what a confident model gets wrong in your Methods — cited.</div>
      </div>

      <Repro />
    </div>
  )
}
