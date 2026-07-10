from verdict.trialval import classify_pair, compute_metrics


def test_classify_pair_covers_the_truth_table():
    assert classify_pair("Ineligible", "excluded") == "correct_ruleout"
    assert classify_pair("Likely eligible", "eligible") == "correct_keep"
    # the two safety failures — a definitive call that contradicts the physician label
    assert classify_pair("Ineligible", "eligible") == "false_exclusion"
    assert classify_pair("Likely eligible", "excluded") == "false_inclusion"
    # abstention is neither right nor wrong; it is honest deferral, split by gold for reporting
    assert classify_pair("Needs verification", "eligible") == "abstain_on_eligible"
    assert classify_pair("Needs verification", "excluded") == "abstain_on_excluded"


def test_compute_metrics():
    records = [
        {"verdict": "Ineligible", "gold": "excluded"},          # correct_ruleout
        {"verdict": "Ineligible", "gold": "excluded"},          # correct_ruleout
        {"verdict": "Needs verification", "gold": "excluded"},   # abstain_on_excluded
        {"verdict": "Likely eligible", "gold": "eligible"},      # correct_keep
        {"verdict": "Needs verification", "gold": "eligible"},   # abstain_on_eligible
        {"verdict": "Ineligible", "gold": "eligible"},           # false_exclusion (confident error)
    ]
    m = compute_metrics(records)
    assert m["n"] == 6
    assert m["coverage"] == 4 / 6                    # 4 definitive calls
    assert m["agreement_when_definitive"] == 3 / 4   # 3 of 4 definitive calls agree
    assert m["confident_error_rate"] == 1 / 6        # the one false_exclusion
    assert m["abstention_rate"] == 2 / 6
    assert m["exclusion_catch_rate"] == 2 / 3        # 2 of 3 excluded pairs correctly ruled out
    assert m["false_inclusion_rate"] == 0 / 3        # never wrongly kept an excluded trial
    assert m["confusion"]["correct_ruleout"] == 2
    assert m["confusion"]["false_exclusion"] == 1


def test_compute_metrics_handles_no_definitive_calls():
    records = [{"verdict": "Needs verification", "gold": "eligible"}]
    m = compute_metrics(records)
    assert m["coverage"] == 0.0
    assert m["agreement_when_definitive"] is None   # undefined, not a divide-by-zero
    assert m["confident_error_rate"] == 0.0
