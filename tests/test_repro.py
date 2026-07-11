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


def test_cell_line_abstains_on_empty_or_unidentifiable_name():
    # A missing / descriptor-only name must ABSTAIN (INSUFFICIENT), never PASS — a PASS on an
    # unidentifiable line can wrongly drive a top-line "Submission-ready". ("abstains, never guesses")
    for name in ["", "   ", "cells", "the cell line", "our lab isolate"]:
        assert repro.check_cell_line(name).result == "INSUFFICIENT", name
    # a real designation with descriptor words still resolves (PASS if not on the register)
    assert repro.check_cell_line("HEK293 cells").result == "PASS"


def test_iclac_does_not_overfire_on_short_generic_tokens():
    # The deterministic gate must NOT emit a confident FAIL + wrong ICLAC citation on short/generic
    # tokens: descriptor-suffixed phrases that reduce to a 2-char fragment ("DD cells" -> "DD"), and
    # generic lab abbreviations / cell-TYPE terms that collide with obscure register keys
    # (AO = acridine orange, EPC = endothelial progenitor cells, OE = overexpression, MS, SC, CO).
    for name in ["DD cells", "SC cells", "EPC", "AO", "OE", "CO", "MS"]:
        f = repro.check_cell_line(name)
        assert f.result != "FAIL", (name, f.result, f.citation)


def test_iclac_still_catches_real_short_and_descriptor_lines():
    # The over-fire guard must NOT create false negatives on genuine misidentified lines: famous
    # short designations (KB=HeLa, FL, HEp-2) and descriptor-laden extractions must still FAIL, cited.
    for name in ["KB", "FL", "HEp-2", "GR-M", "GR-M pancreatic carcinoma line",
                 "SNB-19 glioblastoma line", "SNB19"]:
        f = repro.check_cell_line(name)
        assert f.result == "FAIL", (name, f.result)
        assert f.citation, name


def test_review_survives_call_tool_raise(monkeypatch):
    # call_tool RAISES when the model emits no tool_use block (parse.py:call_tool) — the real failure
    # mode under concurrency / API hiccups (it never returns None). review() must degrade to a valid
    # report, not propagate the exception (which 502s a live "paste your own Methods" run).
    def boom(*a, **k):
        raise RuntimeError("model returned no structured tool call")
    monkeypatch.setattr(repro, "call_tool", boom)
    rep = repro.review("Cells were the GR-M line, cultured in DMEM.")
    assert rep.verdict in ("Needs fixes", "Needs verification", "Submission-ready")
    # a failed extraction fabricates no FAILs — it degrades to "no resources found"
    assert rep.n_fail == 0, rep


def test_aggregate_model_judgment_fail_is_advisory_not_deterministic():
    # The headline verdict is issued by the DETERMINISTIC (rule) gates. A model-judgment FAIL
    # (e.g. a rigor flag Claude set, which could be a hallucination) must not fabricate the
    # deterministic "Needs fixes" — it surfaces as "Needs verification".
    assert aggregate([Finding("x", "rigor", "FAIL", "", method="model judgment")]) == "Needs verification"
    assert aggregate([Finding("x", "cell_line", "FAIL", "", method="rule")]) == "Needs fixes"
    # a deterministic FAIL still dominates
    assert aggregate([Finding("a", "cell_line", "FAIL", "", method="rule"),
                      Finding("b", "rigor", "FAIL", "", method="model judgment")]) == "Needs fixes"


def test_no_catalog_antibody_is_rule_not_model_judgment():
    # No catalog # -> can't authenticate -> abstain. That is a DETERMINISTIC consequence (rule),
    # not a model judgment — antibody-identity checks are registry lookups, and the label must say so.
    f = repro.check_antibody("anti-GFAP", "Dako", "")
    assert f.result == "INSUFFICIENT" and f.method == "rule", (f.result, f.method)


def test_iclac_citation_not_doubled():
    # citation reads "ICLAC-00010 · CVCL_0372", not "ICLAC ICLAC-00010 · ..." (iclac_id already
    # carries the ICLAC- prefix).
    f = repro.check_cell_line("KB")
    assert f.result == "FAIL"
    assert f.citation.startswith("ICLAC-") and "ICLAC ICLAC-" not in f.citation, f.citation


def test_review_includes_knockout_reasoning(monkeypatch):
    # review() runs the knockout-control REASONING gate for each extracted antibody and appends a
    # labelled model-judgment finding — the one place Claude reasons rather than extracts.
    from verdict import knockout
    monkeypatch.setattr(repro, "extract_resources", lambda t: {
        "cell_lines": [], "antibodies": [{"name": "Iba1", "vendor": "Wako", "catalog": ""}], "rigor": {}})
    monkeypatch.setattr(knockout, "call_tool",
                        lambda *a, **k: {"status": "not_reported", "evidence": "", "reasoning": "x"})
    rep = repro.review("Sections were stained with anti-Iba1 (Wako).")
    ko = [f for f in rep.findings if f.kind == "knockout"]
    assert len(ko) == 1, rep.findings
    assert ko[0].method == "model judgment" and ko[0].result == "INSUFFICIENT"
    # a model-judgment finding never fabricates the deterministic "Needs fixes"
    assert rep.verdict in ("Needs verification", "Submission-ready")


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


def test_antibody_vendor_mismatch_abstains(monkeypatch):
    # A vendor is stated that matches NONE of the catalog-matching records. The gate must NOT cite a
    # different vendor's RRID as a PASS — it must abstain. (This is the exact wrong-vendor class the
    # docstring swears never happens; the existing test only covered the vendor-MATCHES path.)
    monkeypatch.setattr(repro, "_ab_cache", lambda: {repro._squash("ab290"): [
        {"accession": 111, "vendorName": "Advanced Targeting Systems", "catalogNum": "AB-290"},
        {"accession": 303395, "vendorName": "Abcam", "catalogNum": "ab290"}]})
    # multi-record catalog collision, stated vendor matches neither -> abstain (not PASS w/ AB_111)
    f = repro.check_antibody("anti-GFP", "Sigma", "ab290")
    assert f.result == "INSUFFICIENT", (f.result, f.citation)
    assert not f.citation, f"a vendor-mismatch abstention must not cite an RRID: {f.citation}"
    # single record, stated vendor mismatches -> abstain (not PASS with the wrong vendor's RRID)
    monkeypatch.setattr(repro, "_ab_cache", lambda: {repro._squash("55-000"): [
        {"accession": 777, "vendorName": "BD Biosciences", "catalogNum": "55-000"}]})
    assert repro.check_antibody("anti-CD3", "Cell Signaling", "55-000").result == "INSUFFICIENT"
