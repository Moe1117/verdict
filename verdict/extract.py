"""Study -> one EvidenceRow. The ONLY generative step in the data path.

Claude reads the abstract/record and fills a structured row with field-level
provenance. It never decides the verdict — it only reports what a study found.
Only NLM-safe metadata + short quoted snippets are used; no verbatim full text
is stored or displayed.
"""
from __future__ import annotations

from .gates import EvidenceRow
from .retrieve import Source


def extract_row(source: Source, abstract: str) -> EvidenceRow:
    """TODO: Claude structured-output call -> EvidenceRow(design, direction,
    population_match, source_id, note). Keep each field traceable to a quote."""
    raise NotImplementedError
