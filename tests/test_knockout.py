from verdict import knockout
from verdict.knockout import KnockoutFinding


def _fixed(status, evidence=""):
    return lambda *a, **k: {"status": status, "evidence": evidence, "reasoning": "because"}


def test_knockout_validated_is_pass(monkeypatch):
    monkeypatch.setattr(knockout, "call_tool", _fixed("validated", "Iba1-knockout tissue showed no signal"))
    f = knockout.assess_knockout_control("... Iba1-knockout tissue showed no signal ...", "Iba1")
    assert isinstance(f, KnockoutFinding)
    assert f.status == "validated" and f.result == "PASS"
    assert f.method == "model judgment"
    assert "knockout" in f.detail.lower()
    assert f.evidence  # carries the verbatim span


def test_knockout_not_reported_abstains(monkeypatch):
    monkeypatch.setattr(knockout, "call_tool", _fixed("not_reported"))
    f = knockout.assess_knockout_control("anti-GFAP (Dako) for astrocytes.", "GFAP")
    assert f.status == "not_reported" and f.result == "INSUFFICIENT"


def test_knockout_ambiguous_abstains(monkeypatch):
    # a bare 'validated' claim with no genetic control described -> abstain, do not credit a PASS
    monkeypatch.setattr(knockout, "call_tool", _fixed("ambiguous", "a validated antibody was used"))
    f = knockout.assess_knockout_control("a validated antibody was used", "CD3")
    assert f.status == "ambiguous" and f.result == "INSUFFICIENT"


def test_knockout_degrades_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("model returned no structured tool call")
    monkeypatch.setattr(knockout, "call_tool", boom)
    f = knockout.assess_knockout_control("...", "Iba1")
    assert f.result == "INSUFFICIENT" and f.status == "not_reported"  # safe default, never crashes


def test_knockout_never_fails(monkeypatch):
    # absence of a validation control is not a deterministic defect to FAIL — the gate only PASSes
    # (validated) or abstains (INSUFFICIENT). It is a labelled model judgment, never a rule FAIL.
    for status in ("validated", "not_reported", "ambiguous", "garbage"):
        monkeypatch.setattr(knockout, "call_tool", _fixed(status))
        f = knockout.assess_knockout_control("x", "Ab")
        assert f.result in ("PASS", "INSUFFICIENT")
        assert f.method == "model judgment"
