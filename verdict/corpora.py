"""Frozen corpora: real, verified EvidenceRows per demo claim.

The demo runs off these frozen JSON files so it is deterministic and needs no
network on stage. Each file is built in-window from public sources (PubMed /
ClinicalTrials.gov) — see PROVENANCE.md. The live pipeline (parse+retrieve+
extract) reproduces them, but the demo does not depend on it.
"""
from __future__ import annotations

import dataclasses
import json
import os

from .gates import EvidenceRow

CORPORA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "benchmark", "corpora")

_FIELDS = {f.name for f in dataclasses.fields(EvidenceRow)}


def _rows_from(data: dict) -> list[EvidenceRow]:
    # Robust to schema drift: keep only known EvidenceRow fields; default citation.
    out = []
    for row in data.get("rows", []):
        d = {k: v for k, v in row.items() if k in _FIELDS}
        d.setdefault("citation", d.get("source_id", ""))
        out.append(EvidenceRow(**d))
    return out


def load_path(path: str) -> tuple[dict, list[EvidenceRow]]:
    with open(path) as fh:
        data = json.load(fh)
    return data, _rows_from(data)


def load_rows(claim_id: str) -> tuple[dict, list[EvidenceRow]]:
    return load_path(os.path.join(CORPORA_DIR, f"{claim_id}.json"))


def available() -> list[str]:
    if not os.path.isdir(CORPORA_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(CORPORA_DIR) if f.endswith(".json"))
