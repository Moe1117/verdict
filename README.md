# Verdict

**A decidable evidence resolver for biomedical claims — one that reports when the evidence is insufficient to decide.**

Paste a claim like *"metformin reduces cancer incidence in adults without diabetes"* and Verdict returns one of four evidence states — **Supported · Not Supported · Contested · Insufficient** — with a calibrated confidence and a full audit ledger tracing every study to the gate it fed. When the evidence cannot decide, Verdict **abstains** rather than overstate.

> ⚕️ **Verdict grades the state of published EVIDENCE for a claim. It is a research and literature-triage tool for professionals. It is NOT medical advice, NOT a diagnosis, and NOT a treatment recommendation.**

Built for the **Built with Claude: Life Sciences** hackathon (Builder track), July 7–13 2026.

## Who it's for

A translational researcher or early-stage biotech scientist triaging a drug-efficacy or drug-repurposing hypothesis — *"is this worth six months?"* — who needs a sourced, rigorous verdict, including an explicit determination that the evidence is not yet sufficient.

## The idea (and why the architecture matters)

Claude does one job: **structured extraction** of evidence from each study (design, N, effect, direction, risk-of-bias). A **deterministic gate engine — with no LLM in the verdict path — issues the verdict.** That means every verdict is a pure, auditable function of the evidence: you can click any verdict and see exactly which studies drove it and which gate each one passed. A calibration layer reports the empirically-measured — and measurably imperfect — reliability of each certainty grade.

This is selective prediction with a measured reject option: certainty is an ordinal grade whose out-of-sample accuracy is measured (High is right ~82%, ECE 0.16 on 82 held-out claims), backed by a distribution-free conformal error bound at High, and it abstains where it cannot be relied upon.

**How well does it work?** Two figures: the deterministic **gate engine** scores 91% with 0 confident false-positives on 32 clinical claims (holding extraction fixed); the **full live product** (Claude extracting from raw PubMed / ClinicalTrials.gov) scores 66% with 3, still far fewer than a plain LLM's 6, and abstains rather than overstate. Both are in [`SUBMISSION.md`](SUBMISSION.md) and reproducible (`scripts/live_benchmark.py`).

## Evidence states

| State | Meaning |
|-------|---------|
| **Supported** | Consistent high-quality evidence (RCTs / meta-analyses) shows the claimed effect |
| **Not Supported** | Sufficient high-quality evidence shows *no* effect / contradicts it (evidence of absence) |
| **Contested** | High-quality evidence genuinely conflicts and doesn't resolve |
| **Insufficient** | Not enough human evidence to decide (absence of evidence) |

`Undecidable` exists only as an *input guard* for ill-posed / unmeasurable claims — not as an evidence verdict.

## Data & attribution

Retrieval uses public sources only:
- **PubMed** via NCBI E-utilities — see the NCBI [disclaimer and usage policy](https://www.ncbi.nlm.nih.gov/home/about/policies/).
- **ClinicalTrials.gov** API — U.S. Government work, public domain.

Verdict displays citation metadata (title, authors, journal, year, PMID/DOI/NCT) and its own extracted structured rows; it does not redistribute copyrighted full text.

## Provenance

See [`PROVENANCE.md`](PROVENANCE.md). Built from scratch during the event; no pre-existing code, data, or benchmark reused.

## Quickstart

```bash
cp .env.example .env       # add your ANTHROPIC_API_KEY and NCBI_EMAIL
pip install -e .
python -m verdict "metformin reduces cancer incidence in adults without diabetes"
```

## License

MIT — see [`LICENSE`](LICENSE).
