"""Every verdict carries a deterministic 'what would change it' — the specific evidence that would
move the verdict, derived from the gate outcome. This turns an abstention into a research directive
(and a decided verdict into its falsifier). No LLM."""
from verdict.directive import research_directive
from verdict.gates import EvidenceRow, GateTrace, Verdict
from verdict.verdict import evaluate


def _t(gate, passed, detail=""):
    return GateTrace(gate, passed, detail)


def test_insufficient_absent_evidence_asks_for_a_trial():
    d = research_directive(Verdict.INSUFFICIENT,
                           [_t("direct-evidence", False, "no on-population randomized/meta evidence — absence of evidence")])
    assert "randomized" in d.lower()
    assert "rct" in d.lower() or "meta-analysis" in d.lower()


def test_insufficient_surrogate_asks_for_the_real_outcome():
    d = research_directive(Verdict.INSUFFICIENT,
                           [_t("direct-evidence", False, "on-population trials measure only surrogate / off-target endpoints")])
    assert "surrogate" in d.lower()


def test_insufficient_thin_asks_for_more_trials():
    d = research_directive(Verdict.INSUFFICIENT,
                           [_t("direct-evidence", True, "1 trial"), _t("sufficiency", False, "only a single small trial on-population")])
    assert any(w in d.lower() for w in ("second", "large", "meta-analysis"))


def test_contested_asks_for_a_tiebreaker():
    d = research_directive(Verdict.CONTESTED, [_t("definitive-evidence", False, "large RCTs themselves conflict")])
    assert "resolve" in d.lower()


def test_decided_verdicts_state_their_falsifier():
    assert "overturn" in research_directive(Verdict.SUPPORTED, []).lower()
    assert "overturn" in research_directive(Verdict.NOT_SUPPORTED, []).lower()


def test_undecidable_asks_to_repose_the_claim():
    assert research_directive(Verdict.UNDECIDABLE, [_t("input-guard", False, "not measurable")])


def test_evaluate_populates_what_would_change_it():
    card = evaluate("drugX reduces mortality in adults",
                    [EvidenceRow(citation="c", design="preclinical", direction=1, population_match=True)])
    assert card.verdict is Verdict.INSUFFICIENT
    assert card.what_would_change_it  # non-empty deterministic directive
