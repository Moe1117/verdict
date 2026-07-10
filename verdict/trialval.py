"""Scoring for the trial-match validation harness — pure, no LLM, no network.

Compares our per-trial verdict against a physician relevance label (TREC 2022 Clinical Trials:
"eligible" or "excluded") using a selective-prediction frame, because the tool is designed to
ABSTAIN rather than guess. So we never reduce it to a single accuracy number that abstention would
dominate; we report three things separately:

  - coverage: how often it makes a definitive call at all (vs "Needs verification")
  - agreement_when_definitive: when it commits, how often it agrees with the physician
  - confident_error_rate: the safety metric — a definitive call that CONTRADICTS the physician
    (ruling out an eligible trial, or keeping an excluded one). This is the "never confidently
    wrong" claim, measured.

Verdict -> action:  "Ineligible" = rule out · "Likely eligible" = keep · "Needs verification" = abstain.
Gold label -> the correct definitive action:  "excluded" = rule out · "eligible" = keep.
"""
from __future__ import annotations

from collections import Counter

_DEFINITIVE = {"Ineligible", "Likely eligible"}


def classify_pair(verdict: str, gold: str) -> str:
    """One (verdict, gold) pair -> an outcome bucket. Pure."""
    if verdict == "Needs verification":
        return "abstain_on_eligible" if gold == "eligible" else "abstain_on_excluded"
    if verdict == "Ineligible":
        return "correct_ruleout" if gold == "excluded" else "false_exclusion"
    if verdict == "Likely eligible":
        return "correct_keep" if gold == "eligible" else "false_inclusion"
    raise ValueError(f"unexpected verdict: {verdict!r}")


_CONFIDENT_ERRORS = {"false_exclusion", "false_inclusion"}
_CORRECT_DEFINITIVE = {"correct_ruleout", "correct_keep"}


def compute_metrics(records: list[dict]) -> dict:
    """records: [{"verdict", "gold", ...}]. Returns the selective-prediction summary. Pure."""
    outcomes = [classify_pair(r["verdict"], r["gold"]) for r in records]
    conf = Counter(outcomes)
    n = len(records)
    n_excluded = sum(1 for r in records if r["gold"] == "excluded")
    n_definitive = sum(1 for r in records if r["verdict"] in _DEFINITIVE)
    n_correct_definitive = conf["correct_ruleout"] + conf["correct_keep"]
    n_confident_error = conf["false_exclusion"] + conf["false_inclusion"]

    return {
        "n": n,
        "n_eligible": sum(1 for r in records if r["gold"] == "eligible"),
        "n_excluded": n_excluded,
        "coverage": n_definitive / n if n else 0.0,
        # None (not 0) when it never commits — agreement is undefined, not perfect and not zero.
        "agreement_when_definitive": (n_correct_definitive / n_definitive) if n_definitive else None,
        "confident_error_rate": n_confident_error / n if n else 0.0,
        "abstention_rate": (conf["abstain_on_eligible"] + conf["abstain_on_excluded"]) / n if n else 0.0,
        # of the trials the physician EXCLUDED, how often did we catch it / dangerously keep it
        "exclusion_catch_rate": (conf["correct_ruleout"] / n_excluded) if n_excluded else None,
        "false_inclusion_rate": (conf["false_inclusion"] / n_excluded) if n_excluded else None,
        "confusion": dict(conf),
    }
