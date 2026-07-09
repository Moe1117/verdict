"""Isolated extraction eval — measures CLAUDE'S EXTRACTION alone, retrieval held fixed.

The live benchmark entangles retrieval + extraction + gates, so a live miss could be Claude
misreading an abstract OR the query missing the study. This isolates extraction: it takes the
EXACT studies already in the curated corpora (their PMIDs), fetches each abstract, runs
extract_row against the corpus's claim, and compares the extracted row field-by-field to the
hand-authored GOLD row. High per-field agreement means Claude's extraction is sound and the
live 91->66 gap is retrieval recall — not the AI-hard extraction step everyone worried about.

Requires ANTHROPIC_API_KEY + NCBI_EMAIL. Per-row cached (resumable).
Usage: PYTHONPATH=. python scripts/extraction_eval.py [--ids C08,M06] [--out web/public/extraction_eval.json]
"""
from __future__ import annotations

import json
import os
import sys
import time

from verdict.corpora import available, load_rows
from verdict.env import load_dotenv
from verdict.extract import extract_row
from verdict.parse import ClaimTuple
from verdict.retrieve import Source, fetch_abstract

RETIRED = {"C09", "F02"}
FIELDS = ["design", "direction", "outcome_match", "population_match", "integrity_ok"]


def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _norm(field: str, v):
    return str(v).strip().lower() if field == "design" else v


def _pmid(source_id: str) -> str | None:
    s = str(source_id)
    return s.split("PMID:")[-1].strip() if s.upper().startswith("PMID") else None


def summarize(rows: dict) -> dict:
    scored = [r for r in rows.values() if "match" in r]
    n = len(scored)
    out = {"n_rows": n, "errors": sum(1 for r in rows.values() if "error" in r)}
    if not n:
        return out
    for f in FIELDS:
        out[f] = round(sum(1 for r in scored if r["match"][f]) / n, 3)
    # direction_polarity = supports-vs-not agreement (what the gates actually use); the two that
    # matter most for a verdict are polarity and outcome_match (the surrogate flag = the value prop).
    out["direction_polarity"] = round(sum(1 for r in scored if r["match"].get("direction_polarity")) / n, 3)
    out["all_fields_exact"] = round(sum(1 for r in scored if all(r["match"][f] for f in FIELDS)) / n, 3)
    return out


def main() -> None:
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("extraction eval needs ANTHROPIC_API_KEY")
    out = _arg("--out", "web/public/extraction_eval.json")
    ids_arg = _arg("--ids", "")
    ids = ids_arg.split(",") if ids_arg else [c for c in available() if c not in RETIRED]

    from verdict.parse import parse_claim
    blob = json.load(open(out)) if os.path.exists(out) else {"rows": {}}
    rows = blob.setdefault("rows", {})
    claims = blob.setdefault("claims", {})
    for cid in ids:
        meta, gold = load_rows(cid)
        if cid not in claims:  # faithful claim decomposition (same as live), one parse per corpus
            ct, _ = parse_claim(meta["claim"])
            claims[cid] = {"agent": ct.agent, "outcome": ct.outcome, "population": ct.population}
            json.dump(blob, open(out, "w"), indent=2)
        c = claims[cid]
        claim = ClaimTuple(raw=meta["claim"], agent=c["agent"], outcome=c["outcome"],
                           population=c["population"], direction=1)
        for g in gold:
            pm = _pmid(g.source_id)
            if not pm:
                continue  # PubMed-only (fetch_abstract); NCT/DOI rows skipped
            key = f"{cid}:PMID{pm}"
            if key in rows and "match" in rows[key]:
                continue
            try:
                abstract = fetch_abstract(f"PMID:{pm}")
                src = Source(kind="pubmed", id=f"PMID:{pm}", title=(g.citation or "")[:140],
                             authors="", journal="", year=str(g.year or ""), url="")
                ex = extract_row(src, abstract, claim)
                match = {f: _norm(f, getattr(ex, f)) == _norm(f, getattr(g, f)) for f in FIELDS}
                # engine-relevant direction: the gates treat -1 and 0 identically (both 'against'),
                # so what matters is the polarity CLASS (supports vs not), not the -1-vs-0 wording.
                match["direction_polarity"] = (ex.direction == 1) == (g.direction == 1)
                rows[key] = {"cid": cid, "pmid": pm,
                             "gold": {f: getattr(g, f) for f in FIELDS},
                             "extracted": {f: getattr(ex, f) for f in FIELDS},
                             "match": match}
            except Exception as e:  # noqa: BLE001
                rows[key] = {"cid": cid, "pmid": pm, "error": f"{type(e).__name__}: {e}"[:150]}
            blob["summary"] = summarize(rows)
            json.dump(blob, open(out, "w"), indent=2)
            m = rows[key].get("match")
            tag = ("all-ok" if m and all(m.values()) else ",".join(f for f, ok in m.items() if not ok)) if m else "ERR"
            print(f"  {key}: {tag}")

    s = blob["summary"]
    print(f"\n=== isolated extraction accuracy (n={s['n_rows']} PubMed rows, {s.get('errors',0)} errored) ===")
    for f in FIELDS:
        if f in s:
            print(f"  {f:20} {s[f]:.0%}")
    if "direction_polarity" in s:
        print(f"  {'direction (polarity)':20} {s['direction_polarity']:.0%}   <- what the gates use")
        print(f"  {'all fields exact':20} {s['all_fields_exact']:.0%}")


if __name__ == "__main__":
    main()
