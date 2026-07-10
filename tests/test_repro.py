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


def test_aggregate_truth_table():
    assert aggregate([Finding("x", "cell_line", "FAIL", "")]) == "Needs fixes"
    assert aggregate([Finding("x", "rigor", "INSUFFICIENT", "")]) == "Needs verification"
    assert aggregate([Finding("x", "cell_line", "PASS", "")]) == "Submission-ready"
    # a FAIL dominates an INSUFFICIENT
    assert aggregate([Finding("a", "cell_line", "FAIL", ""), Finding("b", "rigor", "INSUFFICIENT", "")]) == "Needs fixes"
