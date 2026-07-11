from verdict import repro
from verdict.repro import Finding, aggregate


def test_iclac_catches_misidentified_even_with_descriptors_and_hyphen_variance():
    # extractors return descriptor-laden or hyphen-varied names — the gate must still fire, cited
    for name in ["GR-M pancreatic carcinoma line", "SNB-19 glioblastoma line", "SNB19", "GR-M"]:
        f = repro.check_cell_line(name)
        assert f.result == "FAIL", name
        assert f.citation, f"a FAIL must be citable: {name}"


def test_iclac_passes_legitimate_lines_no_false_positive():
    for name in ["MCF-7 breast cancer cells", "HEK293 cells", "the primary cortical neurons"]:
        assert repro.check_cell_line(name).result == "PASS", name


def test_review_survives_none_extraction(monkeypatch):
    # call_tool returns None intermittently under concurrency — the pipeline must degrade, not crash
    monkeypatch.setattr(repro, "call_tool", lambda *a, **k: None)
    rep = repro.review("Cells were the GR-M line, cultured in DMEM.")
    assert rep.verdict in ("Needs fixes", "Needs verification", "Submission-ready")


def test_aggregate_truth_table():
    assert aggregate([Finding("x", "cell_line", "FAIL", "")]) == "Needs fixes"
    assert aggregate([Finding("x", "rigor", "INSUFFICIENT", "")]) == "Needs verification"
    assert aggregate([Finding("x", "cell_line", "PASS", "")]) == "Submission-ready"
    # a FAIL dominates an INSUFFICIENT
    assert aggregate([Finding("a", "cell_line", "FAIL", ""), Finding("b", "rigor", "INSUFFICIENT", "")]) == "Needs fixes"


def test_antibody_requires_matching_catalog(monkeypatch):
    # a bare name (no catalog) must abstain, never PASS
    assert repro.check_antibody("anti-GFAP", "Dako", "").result == "INSUFFICIENT"
    # a catalog that resolves to a DIFFERENT vendor must not be cited as a PASS for the queried vendor
    monkeypatch.setattr(repro, "_ab_cache", lambda: {repro._squash("ab290"): [
        {"accession": 111, "vendorName": "Advanced Targeting Systems", "catalogNum": "AB-290"},
        {"accession": 303395, "vendorName": "Abcam", "catalogNum": "ab290"}]})
    f = repro.check_antibody("anti-GFP", "Abcam", "ab290")
    assert f.result == "PASS" and f.citation == "RRID:AB_303395", (f.result, f.citation)
    # same catalog, wrong/absent vendor + two vendors -> ambiguous -> abstain
    assert repro.check_antibody("anti-GFP", "", "ab290").result == "INSUFFICIENT"
