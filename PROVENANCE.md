# Provenance

**Built from scratch during Built with Claude: Life Sciences (July 7–13, 2026).**

This project reused **none** of the author's prior commercial work — no code, no data, no benchmark, and no labels from RegCheck360 (a regulatory-compliance product the author previously built). The only thing carried over is the *general idea* that some claims are decidable by deterministic rules rather than by a language model's guess. The gate rules, calibration, retrieval, extraction, benchmark, and UI in this repository were all authored during the event.

- **First commit** is timestamped after the July 7 kickoff; the git history is the record of in-window construction.
- **Benchmark** (`benchmark/claims.yaml`): the gold labels were assigned during the event, and every cited source is re-derived independently from **PubMed E-utilities** and **ClinicalTrials.gov** (public-domain / open sources). The benchmark reproduces from those public sources alone.
- **Consensus** was used only as a *build-time grounding aid* while researching the benchmark. **No Consensus output is redistributed** in this repository, and Verdict does not call Consensus at runtime.
- **Methods Verifier (the Builder-track entry):** the bundled register (`benchmark/repro/iclac_register.json`) is transcribed from the public **ICLAC Register of Misidentified Cell Lines** + **Cellosaurus** (CVCL) identifiers; antibody RRIDs resolve live against the public **Antibody Registry**; rigor items check **ARRIVE 2.0 / MDAR / NIH** policy presence. The scorecards in `benchmark/repro/*.json` were generated in-window by `scripts/repro_iclac_benchmark.py` and `scripts/repro_stress_test.py`, and every displayed number ties back to those files. The knockout-control gate's real-manuscript corpus (`benchmark/repro/knockout_corpus_real.json`) draws its cases from 6 open-access papers (PMIDs cited in the file); to stay copyright-clean and free of PMC full-text extraction artifacts, each Methods snippet is a **faithful paraphrase** of the cited paper's reported validation approach — not a verbatim quote — while the antibody, target, approach, and label reflect what the paper actually reports (verifiable by PMID).
- **AI assistance:** this is a Claude Code Builder-track project; it was authored with Claude Code, which is the intended tool of the hackathon.

Any headline accuracy figure reported for Verdict is computed from the in-window benchmark in this repo. Prior results from other projects are cited, where mentioned at all, strictly as the author's background motivation — never as a Verdict result.
