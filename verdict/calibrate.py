"""Honest calibration + selective prediction for the deterministic engine.

The thesis promises "calibrated confidence": that when Verdict reports a certainty
level, that level means an empirically-measured accuracy. This module delivers it the
only way ~100 labels can honestly support — NOT by fitting a smooth calibrator
(isotonic/Platt on 100 points overfits), but by measuring the observed accuracy of
each coarse certainty bucket with a Wilson 95% CI, refusing to emit a number for a
bucket too thin to support one, and reporting a reliability diagram, a risk–coverage
(accuracy-vs-coverage) curve, and the expected calibration error (ECE).

Fit on the DEV split (the frozen benchmark) only; the held-out split is used solely as
an out-of-sample check. No gate threshold or bucket is ever tuned to raise a number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .certainty import LEVELS

MIN_SUPPORT = 5  # buckets thinner than this report "insufficient calibration data"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI for a binomial proportion k/n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass
class Bucket:
    level: str
    n: int
    correct: int
    accuracy: float | None       # None when n < MIN_SUPPORT
    ci: tuple[float, float] | None


@dataclass
class Calibration:
    buckets: dict[str, Bucket]                    # keyed by certainty level
    n_total: int
    ece: float                                    # expected calibration error
    reliability: list[dict] = field(default_factory=list)     # per-level predicted vs observed
    risk_coverage: list[dict] = field(default_factory=list)   # accuracy vs coverage sweep

    def confidence_for(self, level: str) -> str:
        b = self.buckets.get(level)
        if b is None or b.accuracy is None:
            return "insufficient calibration data"
        lo, hi = b.ci
        return f"{b.accuracy:.0%} (95% CI {lo:.0%}-{hi:.0%}, n={b.n})"


def fit(cases: list[tuple[str, bool]]) -> Calibration:
    """cases = [(certainty_level, correct?)] on the DEV split. Returns the calibration."""
    buckets: dict[str, Bucket] = {}
    for lvl in LEVELS:
        rows = [ok for (l, ok) in cases if l == lvl]
        n, k = len(rows), sum(rows)
        if n >= MIN_SUPPORT:
            buckets[lvl] = Bucket(lvl, n, k, k / n, wilson(k, n))
        else:
            buckets[lvl] = Bucket(lvl, n, k, None, None)
    # ECE over the certainty bins: |predicted - observed| weighted by bin size. The
    # predicted confidence of a bin is its own dev accuracy, so on the dev split ECE is
    # ~0 by construction; the meaningful ECE is computed out-of-sample (see report()).
    n_total = len(cases)
    return Calibration(buckets=buckets, n_total=n_total, ece=0.0)


def risk_coverage(scored: list[tuple[int, bool]]) -> list[dict]:
    """scored = [(certainty_score 0..3, correct?)]. Sweep the minimum-certainty threshold:
    at each level, 'coverage' = fraction the engine will commit to (certainty >= t) and
    'accuracy' = accuracy among those. The measured accuracy/abstention trade-off."""
    n = len(scored)
    out = []
    for t in (0, 1, 2, 3):
        answered = [ok for (s, ok) in scored if s >= t]
        if not answered:
            continue
        out.append({
            "min_certainty": LEVELS[t],
            "coverage": round(len(answered) / n, 3),
            "accuracy": round(sum(answered) / len(answered), 3),
            "n_answered": len(answered),
        })
    return out


def ece(dev: Calibration, eval_cases: list[tuple[str, bool]]) -> float:
    """Out-of-sample ECE: for each bin, |dev-predicted-accuracy - observed-accuracy-on-eval|
    weighted by the bin's share of the eval set. Bins with no dev prediction are skipped."""
    n = len(eval_cases) or 1
    total = 0.0
    for lvl in LEVELS:
        b = dev.buckets.get(lvl)
        if b is None or b.accuracy is None:
            continue
        rows = [ok for (l, ok) in eval_cases if l == lvl]
        if not rows:
            continue
        observed = sum(rows) / len(rows)
        total += (len(rows) / n) * abs(b.accuracy - observed)
    return round(total, 4)
