"""Distribution-free selective-risk guarantee (conformal risk control).

calibrate.py reports the OBSERVED accuracy per certainty bucket. conformal.py turns
'commit only above a certainty threshold' into a GUARANTEED operating point: on a calibration
split, pick the lowest certainty threshold whose exact Clopper-Pearson upper confidence bound
on the committed error rate is <= a target risk alpha; that carries a finite-sample,
distribution-free guarantee. The held-out split VERIFIES it out of sample — it never chooses it.
"""
from verdict.conformal import certify, certify_pooled, cp_upper


def test_cp_upper_zero_errors_matches_closed_form():
    # 0 errors in 21 trials at 90% confidence -> 1 - 0.1**(1/21) ~= 0.103
    ub = cp_upper(0, 21, 0.1)
    assert 0.09 < ub < 0.12


def test_cp_upper_is_monotone_in_errors():
    assert cp_upper(0, 50, 0.1) < cp_upper(5, 50, 0.1) < cp_upper(20, 50, 0.1)


def test_cp_upper_bounds_the_point_estimate():
    # an upper CONFIDENCE bound must exceed the observed error rate
    assert cp_upper(5, 50, 0.1) > 5 / 50


def test_certify_meets_target_and_validates_out_of_sample():
    cal = [(3, True)] * 20 + [(2, True)] * 3 + [(2, False)] * 3 + [(1, False)] * 6
    held = [(3, True)] * 18 + [(3, False)] * 2 + [(2, True)] * 5 + [(2, False)] * 5
    g = certify(cal, held, alpha=0.2, delta=0.1)
    assert g.cal_error_ucb <= 0.2          # the chosen threshold's UCB meets the target
    assert g.threshold_score >= 2          # it had to exclude the noisy low-certainty claims
    assert g.guarantee_held is True        # verified on held-out (10% error <= 20%)
    assert 0.0 <= g.heldout_error <= 1.0


def test_certify_is_honest_when_target_unreachable():
    cal = [(3, True)] * 10 + [(3, False)] * 5
    g = certify(cal, [], alpha=0.01, delta=0.1)
    assert g.cal_error_ucb > 0.01          # can't guarantee 1% error from this data — says so
    assert g.guarantee_held is None        # no held-out set to verify against


def test_pooled_guarantee_holds_under_exchangeability():
    # an exchangeable pool where High is clean: the guarantee should hold on the large majority
    # of random calibration/test splits, and mean test error should be near the target.
    pool = [(3, True)] * 70 + [(3, False)] * 3 + [(1, True)] * 5 + [(1, False)] * 22
    g = certify_pooled(pool, alpha=0.2, delta=0.1, k=100, seed=0)
    assert g.n_splits == 100
    assert g.frac_guarantee_held >= 0.8    # holds across most random (exchangeable) splits
    assert g.mean_test_error <= 0.2
