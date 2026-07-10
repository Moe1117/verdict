from verdict import trialmatch


def test_profile_from_tool_json():
    payload = {"age": 62, "age_src": "62-year-old woman", "sex": "FEMALE",
               "diagnosis": "metastatic NSCLC", "biomarkers": ["EGFR exon 19 deletion"],
               "prior_therapies": ["osimertinib"], "ecog": 1, "labs": {}, "cns_status": None}
    p = trialmatch.profile_from_json(payload, raw_note="62F ...")
    assert p.age == 62 and p.sex == "FEMALE" and "EGFR exon 19 deletion" in p.biomarkers


def test_criteria_from_tool_json():
    payload = {"criteria": [
        {"id": "inc1", "kind": "inclusion", "ctype": "structured", "predicate": "Aged 18-75",
         "source_text": "Aged 18-75", "field": "age", "op": "range", "lo": 18, "hi": 75},
        {"id": "exc1", "kind": "exclusion", "ctype": "semantic",
         "predicate": "active CNS metastasis", "source_text": "Patients with active CNS metastasis"}]}
    crits = trialmatch.criteria_from_json(payload)
    assert crits[0].field == "age" and crits[1].ctype == "semantic"
