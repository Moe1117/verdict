"""Distribution-free selective-risk guarantee for the abstention boundary.

The calibration layer (calibrate.py) reports the OBSERVED accuracy of each certainty bucket —
a descriptive statistic. This adds a GUARANTEE. Frame the engine as a selective classifier:
"commit to the verdict only when certainty >= t, otherwise abstain." For a target committed-
error rate alpha, pick — on a CALIBRATION split only — the lowest threshold t whose exact
Clopper-Pearson upper confidence bound on the committed error is <= alpha. That threshold then
carries a finite-sample, distribution-free guarantee (it assumes only that the data are
exchangeable — no parametric model, no asymptotics). The HELD-OUT split is used solely to
verify the guarantee holds out of sample; it never influences the choice.

Clopper-Pearson is computed by bisection on the exact binomial CDF, so there is no numerical
dependency (no scipy/numpy) and the bound is exact, not an approximation.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import comb


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 1.0 if k >= n else 0.0
    return sum(comb(n, i) * p ** i * (1.0 - p) ** (n - i) for i in range(0, k + 1))


def cp_upper(errors: int, n: int, delta: float) -> float:
    """Exact Clopper-Pearson upper confidence bound on the error probability given `errors`
    failures in `n` trials, valid with probability >= 1 - delta. Monotone bisection: the bound
    p_u is the largest p for which P(X <= errors; n, p) >= delta."""
    if n == 0 or errors >= n:
        return 1.0
    lo, hi = errors / n, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _binom_cdf(errors, n, mid) > delta:  # still plausible -> push the bound higher
            lo = mid
        else:
            hi = mid
    return hi


@dataclass
class Guarantee:
    alpha: float                    # target committed-error rate
    delta: float                    # the bound holds with probability >= 1 - delta
    threshold_score: int            # commit iff certainty score >= this (0..3)
    threshold_level: str            # human label of the threshold
    cal_error: float                # observed committed error on the calibration split
    cal_error_ucb: float            # Clopper-Pearson upper bound on it (<= alpha when guaranteed)
    cal_coverage: float             # fraction of calibration claims committed
    n_committed: int
    guaranteed: bool                # was a threshold found whose UCB <= alpha?
    heldout_error: float | None     # realized committed error on the disjoint held-out split
    heldout_coverage: float | None
    guarantee_held: bool | None     # heldout_error <= alpha ? (None if no held-out split)


def _selective(scored: list[tuple[int, bool]], t: int) -> tuple[int, int]:
    """Return (errors, n_committed) among claims with certainty score >= t."""
    committed = [ok for (s, ok) in scored if s >= t]
    return sum(1 for ok in committed if not ok), len(committed)


def certify(cal_scored: list[tuple[int, bool]], held_scored: list[tuple[int, bool]],
            alpha: float = 0.2, delta: float = 0.1, levels: list[str] | None = None) -> Guarantee:
    """Pick the most permissive certainty threshold that guarantees committed error <= alpha on
    the calibration split, then report whether it held on the held-out split."""
    if levels is None:
        from .certainty import LEVELS
        levels = LEVELS
    chosen = None
    for t in range(len(levels)):  # 0 (commit everything) .. up to the strictest
        err, n = _selective(cal_scored, t)
        if n == 0:
            continue
        ucb = cp_upper(err, n, delta)
        if ucb <= alpha:
            chosen = (t, err, n, ucb, True)
            break
    if chosen is None:  # even the strictest threshold cannot guarantee alpha — report it honestly
        t = len(levels) - 1
        err, n = _selective(cal_scored, t)
        chosen = (t, err, n, cp_upper(err, n, delta) if n else 1.0, False)

    t, err, n, ucb, guaranteed = chosen
    held_err = held_n = None
    guarantee_held = None
    if held_scored:
        he, hn = _selective(held_scored, t)
        held_err = he / hn if hn else None
        held_n = hn
        guarantee_held = (held_err is not None and held_err <= alpha)

    return Guarantee(
        alpha=alpha, delta=delta, threshold_score=t, threshold_level=levels[t],
        cal_error=(err / n if n else 1.0), cal_error_ucb=ucb,
        cal_coverage=(n / len(cal_scored) if cal_scored else 0.0), n_committed=n,
        guaranteed=guaranteed,
        heldout_error=held_err,
        heldout_coverage=(held_n / len(held_scored) if held_scored and held_n is not None else None),
        guarantee_held=guarantee_held,
    )


@dataclass
class PooledGuarantee:
    alpha: float
    delta: float
    n_splits: int
    modal_threshold_level: str
    mean_test_error: float          # mean realized error on the test half, across splits
    mean_coverage: float
    frac_guarantee_held: float      # fraction of splits whose test error <= alpha


def certify_pooled(scored: list[tuple[int, bool]], alpha: float = 0.2, delta: float = 0.1,
                   k: int = 200, seed: int = 0, levels: list[str] | None = None) -> PooledGuarantee:
    """The correct conformal demonstration: over k random calibration/test splits of an
    EXCHANGEABLE pool, choose the threshold on the calibration half and measure the realized
    error on the test half. Deterministic (fixed seed) so it is reproducible."""
    if levels is None:
        from .certainty import LEVELS
        levels = LEVELS
    rng = random.Random(seed)
    data = list(scored)
    test_errors: list[float] = []
    coverages: list[float] = []
    held: list[bool] = []
    thresholds: list[int] = []
    for _ in range(k):
        idx = list(range(len(data)))
        rng.shuffle(idx)
        half = len(idx) // 2
        cal = [data[i] for i in idx[:half]]
        test = [data[i] for i in idx[half:]]
        g = certify(cal, test, alpha, delta, levels)
        thresholds.append(g.threshold_score)
        if g.heldout_error is not None:
            test_errors.append(g.heldout_error)
            coverages.append(g.heldout_coverage or 0.0)
            held.append(bool(g.guarantee_held))
    modal = max(set(thresholds), key=thresholds.count) if thresholds else len(levels) - 1
    return PooledGuarantee(
        alpha=alpha, delta=delta, n_splits=k, modal_threshold_level=levels[modal],
        mean_test_error=(sum(test_errors) / len(test_errors) if test_errors else 1.0),
        mean_coverage=(sum(coverages) / len(coverages) if coverages else 0.0),
        frac_guarantee_held=(sum(1 for h in held if h) / len(held) if held else 0.0),
    )
