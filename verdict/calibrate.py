"""Calibration: map a gate configuration to an empirically-calibrated confidence.

Fit on the labeled dev split of the benchmark (isotonic or Platt). "0.9" must
mean ~90% correct. Small N -> report bootstrap CIs and be explicit about limits;
never imply a robust guarantee the sample can't support.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Calibrated:
    confidence: float
    n_support: int         # how many benchmark cases back this gate config
    ci: tuple[float, float]


def fit(dev_records: list[dict]) -> "Calibrator":
    """TODO: fit isotonic/Platt from gate-config -> correctness on the dev split."""
    raise NotImplementedError


class Calibrator:
    def confidence_for(self, gate_signature: str) -> Calibrated:  # noqa: D401
        """TODO: return calibrated confidence + CI for a gate signature."""
        raise NotImplementedError
