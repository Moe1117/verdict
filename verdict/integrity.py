"""Integrity guardrail.

A study is flagged as integrity-compromised ONLY when a citable public record
exists (retraction, expression of concern, or a named peer-reviewed reanalysis).
The flag echoes the *source's own* severity wording and links the source. If no
such record exists, the status is "not assessed" — never an unfounded accusation.

Extend INTEGRITY_RECORDS only with entries backed by a real, citable URL.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrityRecord:
    severity: str        # "retracted" | "expression_of_concern" | "reanalysis_concern"
    wording: str         # display text — mirror the source's own language
    source_url: str      # the citable public record


# Seed registry. Each entry MUST have a verifiable source_url before demo/submit.
INTEGRITY_RECORDS: dict[str, IntegrityRecord] = {
    # Ivermectin/COVID — the demo case. Verify and paste exact source URLs.
    "elgazzar-2021-ivermectin": IntegrityRecord(
        severity="retracted",
        wording="RETRACTED — withdrawn over data-integrity concerns (fabrication)",
        source_url="TODO: paste Research Square retraction notice URL",
    ),
    "niaee-2021-ivermectin": IntegrityRecord(
        severity="expression_of_concern",
        wording="Expression of Concern — integrity questioned, not resolved (NOT retracted)",
        source_url="TODO: paste the journal Expression of Concern URL",
    ),
}


def screen(study_key: str) -> IntegrityRecord | None:
    """Return the integrity record for a study, or None => 'integrity: not assessed'."""
    return INTEGRITY_RECORDS.get(study_key)


def status_text(study_key: str) -> str:
    rec = screen(study_key)
    return rec.wording if rec else "integrity status: not assessed"
