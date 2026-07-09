"""Fit the certainty calibration on the DEV benchmark, validate it out-of-sample on the
held-out sets, and emit reliability / risk-coverage / ECE. Writes web/public/calibration.json.

DEV = the clinical benchmark corpora (fit here only). HELD-OUT = benchmark/heldout* (the
frozen out-of-sample check). No threshold is tuned to any of these numbers.
"""
from __future__ import annotations

import json
import os

from verdict.calibrate import LEVELS, ece, fit, risk_coverage
from verdict.certainty import grade_certainty
from verdict.conformal import certify, certify_pooled
from verdict.corpora import available, load_path, load_rows
from verdict.gates import resolve

ROOT = os.path.dirname(os.path.dirname(__file__))
WEB = os.path.join(ROOT, "web", "public")
RETIRED = {"C09", "F02"}  # fringe/supplement, retired from the clinical benchmark


def _cases(items):
    """items = [(claim_id, rows, gold)] -> [(level, score, correct)]."""
    out = []
    for cid, rows, gold in items:
        v = resolve(rows)[0]
        c = grade_certainty(rows, v)
        out.append((c.level, c.score, v.value == gold))
    return out


def _dev_items():
    for cid in available():
        if cid in RETIRED:
            continue
        meta, rows = load_rows(cid)
        yield cid, rows, meta["expected_verdict"]


def _heldout_items():
    for sub in ("heldout", "heldout_v2", "heldout_v3"):
        d = os.path.join(ROOT, "benchmark", sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                meta, rows = load_path(os.path.join(d, f))
                yield f[:-5], rows, meta["expected_verdict"]


def main() -> None:
    dev = _cases(list(_dev_items()))
    held = _cases(list(_heldout_items()))

    # Headline "what a certainty level empirically means" = pooled frequency over ALL labeled
    # claims (largest honest sample; a descriptive statistic, nothing is tuned).
    cal = fit([(lvl, ok) for (lvl, _s, ok) in dev + held])
    # Separately, the out-of-sample CHECK: a calibration fit on DEV only, tested on held-out.
    dev_cal = fit([(lvl, ok) for (lvl, _s, ok) in dev])
    held_lvl = [(lvl, ok) for (lvl, _s, ok) in held]
    ece_oos = ece(dev_cal, held_lvl)

    # reliability: dev-predicted accuracy vs held-out observed accuracy, per certainty level
    reliability = []
    for lvl in LEVELS:
        b = dev_cal.buckets[lvl]
        hk = [ok for (l, ok) in held_lvl if l == lvl]
        reliability.append({
            "level": lvl,
            "predicted": round(b.accuracy, 3) if b.accuracy is not None else None,
            "dev_n": b.n,
            "observed_heldout": round(sum(hk) / len(hk), 3) if hk else None,
            "heldout_n": len(hk),
        })

    rc = risk_coverage([(s, ok) for (_l, s, ok) in dev + held])

    # Conformal selective-risk guarantee (distribution-free, under exchangeability). Demonstrated
    # on random calibration/test splits of the pooled labels; the dev->held split is NOT
    # exchangeable (a deliberate covariate shift), so we report that boundary honestly.
    pooled = [(s, ok) for (_l, s, ok) in dev + held]
    conf = certify_pooled(pooled, alpha=0.20, delta=0.10, k=500, seed=0)
    shift = certify([(s, ok) for (_l, s, ok) in dev], [(s, ok) for (_l, s, ok) in held],
                    alpha=0.20, delta=0.10)

    report = {
        "note": "Certainty calibration fit on the DEV benchmark; validated out-of-sample on the "
                "held-out sets. Buckets with n<5 report no number (measured reject option). "
                "No gate or threshold is tuned to these figures.",
        "dev_n": len(dev),
        "heldout_n": len(held),
        "ece_out_of_sample": ece_oos,
        "buckets": [
            {"level": lvl, "n": cal.buckets[lvl].n,
             "accuracy": round(cal.buckets[lvl].accuracy, 3) if cal.buckets[lvl].accuracy is not None else None,
             "ci": [round(x, 3) for x in cal.buckets[lvl].ci] if cal.buckets[lvl].ci else None,
             "confidence": cal.confidence_for(lvl)}
            for lvl in LEVELS
        ],
        "reliability": reliability,
        "risk_coverage": rc,
        "conformal": {
            "alpha": conf.alpha, "delta": conf.delta, "threshold": conf.modal_threshold_level,
            "mean_test_error": round(conf.mean_test_error, 3), "coverage": round(conf.mean_coverage, 3),
            "guarantee_held_fraction": round(conf.frac_guarantee_held, 3), "n_splits": conf.n_splits,
            "covariate_shift_heldout_error": round(shift.heldout_error, 3) if shift.heldout_error is not None else None,
            "note": (f"Distribution-free selective-risk guarantee: committing only at >= "
                     f"{conf.modal_threshold_level} certainty holds committed error <= {conf.alpha:.0%} with "
                     f"probability >= {1 - conf.delta:.0%} under exchangeability; empirically held in "
                     f"{conf.frac_guarantee_held:.0%} of {conf.n_splits} random splits (mean error "
                     f"{conf.mean_test_error:.0%}, coverage {conf.mean_coverage:.0%}). It does NOT transfer "
                     f"to the covariate-shifted held-out set ({shift.heldout_error:.0%} realized error) — "
                     "the honest boundary of the guarantee."),
        },
    }
    os.makedirs(WEB, exist_ok=True)
    json.dump(report, open(os.path.join(WEB, "calibration.json"), "w"), indent=2)

    print(f"=== Certainty calibration (dev n={len(dev)}, held-out n={len(held)}) ===\n")
    print(f"Per certainty level — pooled accuracy across all {len(dev) + len(held)} labeled claims"
          " (what 'confidence' MEANS):")
    for lvl in reversed(LEVELS):
        print(f"  {lvl:10} {cal.confidence_for(lvl)}")
    print(f"\nOut-of-sample calibration error (ECE) on held-out: {ece_oos}")
    print("\nReliability (dev-predicted vs held-out-observed accuracy):")
    for r in reversed(reliability):
        p = f"{r['predicted']:.0%}" if r["predicted"] is not None else "  — "
        o = f"{r['observed_heldout']:.0%}" if r["observed_heldout"] is not None else "  — "
        print(f"  {r['level']:10} predicted {p:>5} (n={r['dev_n']:>2})  |  observed {o:>5} (n={r['heldout_n']:>2})")
    print("\nRisk–coverage (answer only when certainty >= threshold):")
    for r in rc:
        print(f"  >= {r['min_certainty']:10} coverage {r['coverage']:.0%}  accuracy {r['accuracy']:.0%}  (n={r['n_answered']})")

    print(f"\nConformal selective-risk guarantee (distribution-free, delta={conf.delta:.0%}):")
    print(f"  commit >= {conf.modal_threshold_level}: committed error <= {conf.alpha:.0%} held in "
          f"{conf.frac_guarantee_held:.0%} of {conf.n_splits} exchangeable splits "
          f"(mean error {conf.mean_test_error:.0%}, coverage {conf.mean_coverage:.0%})")
    print(f"  boundary — does NOT transfer to the covariate-shifted held-out set "
          f"({shift.heldout_error:.0%} realized error)")


if __name__ == "__main__":
    main()
