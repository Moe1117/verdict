"""Freeze gathered evidence into benchmark/corpora/*.json (parses n_int + year).

Usage: python scripts/freeze_corpora.py <gathered.json>

Input is the corpora-gathering result: {"corpora": [{claim_id, expected_verdict,
rows, integrity_records}]} (a raw workflow-wrapper {"result": ...} is unwrapped).
Rows carry ONLY PMIDs/NCTs/DOIs — no Consensus output. See PROVENANCE.md.
"""
from __future__ import annotations

import json
import os
import re
import sys

CLAIMS = {
    "C08": "Ivermectin improves clinical outcomes in COVID-19",
    "C09": "Fenbendazole treats cancer in humans",
    "C01": "Atorvastatin reduces LDL cholesterol in adults with hyperlipidemia",
    "C12": "Curcumin improves memory in healthy adults",
    "C05": "Metformin reduces cancer incidence in adults without diabetes",
}
OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "benchmark", "corpora")


def _n_int(s: str) -> int:
    m = re.search(r"(\d[\d,]*)", str(s or ""))
    return int(m.group(1).replace(",", "")) if m else 0


def _year(cit: str) -> int:
    m = re.search(r"\b(19|20)\d{2}\b", str(cit or ""))
    return int(m.group(0)) if m else 0


def main(path: str) -> None:
    data = json.load(open(path))
    if "result" in data:
        data = data["result"] if isinstance(data["result"], dict) else json.loads(data["result"])
    os.makedirs(OUT, exist_ok=True)
    for c in data["corpora"]:
        cid = c["claim_id"]
        for r in c["rows"]:
            r["n_int"] = r.get("n_int") or _n_int(r.get("n", ""))
            r["year"] = r.get("year") or _year(r.get("citation", ""))
        rec = {
            "claim_id": cid,
            "claim": c.get("claim") or CLAIMS.get(cid, cid),
            "expected_verdict": c["expected_verdict"],
            "rows": c["rows"],
            "integrity_records": c.get("integrity_records", []),
            "provenance": "Gathered in-window from PubMed/ClinicalTrials.gov (public). PMIDs/NCTs/DOIs only; no Consensus output redistributed.",
        }
        with open(os.path.join(OUT, f"{cid}.json"), "w") as fh:
            json.dump(rec, fh, indent=2)
        print(f"wrote {cid}.json ({len(c['rows'])} rows)")


if __name__ == "__main__":
    main(sys.argv[1])
