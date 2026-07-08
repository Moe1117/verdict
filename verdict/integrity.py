"""Integrity guardrail.

A study is flagged as integrity-compromised ONLY when a citable public record
exists (retraction, expression of concern, or a named peer-reviewed reanalysis).
The flag mirrors the source's own severity wording and links the source. If no
such record exists, the status is "not assessed" — never an unfounded accusation.

Extend INTEGRITY_RECORDS only with entries backed by a real, citable URL.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrityRecord:
    severity: str        # "retracted" | "expression_of_concern" | "reanalysis_concern"
    wording: str         # display text — mirrors the source's own language
    source_url: str      # the citable public record


# Verified records only. Each MUST have a real source_url.
INTEGRITY_RECORDS: dict[str, IntegrityRecord] = {
    # The influential ivermectin/COVID trial (Elgazzar). Withdrawn by Research
    # Square in July 2021 for ethical / data-integrity concerns (plagiarism,
    # data problems). This is the demo's integrity case — well documented.
    "elgazzar-2021-ivermectin": IntegrityRecord(
        severity="retracted",
        wording="RETRACTED — withdrawn by Research Square (Jul 2021) over ethical / data-integrity concerns",
        source_url="https://retractionwatch.com/2021/11/02/ivermectin-covid-19-study-retracted-authors-blame-file-mixup/",
    ),
    # NOTE — deliberately NOT included: the Niaee 2021 trial. The Expression of
    # Concern in this saga applied to the ivermectin *meta-analyses* that pooled
    # flawed studies, not to the Niaee trial itself. Flagging Niaee as
    # compromised without a study-specific citable record would be unfounded.
    # Do not add it back without a real retraction/EoC URL for that study.
}


def screen(study_key: str) -> IntegrityRecord | None:
    """Return the integrity record for a study, or None => 'not assessed'."""
    return INTEGRITY_RECORDS.get(study_key)


def status_text(study_key: str) -> str:
    rec = screen(study_key)
    return rec.wording if rec else "integrity status: not assessed"
