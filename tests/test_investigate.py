from verdict import investigate
from verdict.investigate import Citation, Investigation, verify_citations


# ---- Task 1: citation-verification grounding gate -------------------------------------------------

def test_ungrounded_found_downgrades_to_abstain():
    # a FOUND verdict whose cited IDs were never retrieved must downgrade to abstain
    inv = Investigation(kind="antibody", verdict="FOUND_VALIDATION",
                        cited=[Citation(id="PMID:999", kind="pubmed", title="x", why="y")],
                        reasoning="r", steps=["searched"], grounded=False)
    out = verify_citations(inv, retrieved={"PMID:111"})  # 999 not retrieved
    assert out.verdict == "NO_VALIDATION_FOUND"
    assert out.cited == [] and out.grounded is False


def test_grounded_found_keeps_only_retrieved_citations():
    inv = Investigation(kind="antibody", verdict="FOUND_VALIDATION",
                        cited=[Citation(id="PMID:111", kind="pubmed", title="real", why="KO"),
                               Citation(id="PMID:999", kind="pubmed", title="hallucinated", why="z")],
                        reasoning="r", steps=[], grounded=False)
    out = verify_citations(inv, retrieved={"PMID:111"})
    assert out.verdict == "FOUND_VALIDATION"
    assert [c.id for c in out.cited] == ["PMID:111"]  # 999 stripped
    assert out.grounded is True


def test_provenance_downgrades_to_partial_without_grounded_reference():
    inv = Investigation(kind="cell_line", verdict="PROVENANCE_CHAIN",
                        cited=[Citation(id="CVCL_2451", kind="cellosaurus", title="", why="")],
                        reasoning="r", steps=[], grounded=False)
    # CVCL grounded but no PubMed primary reference retrieved -> PARTIAL (still grounded on the CVCL)
    out = verify_citations(inv, retrieved={"CVCL_2451"})
    assert out.verdict == "PARTIAL"
    assert out.grounded is True
