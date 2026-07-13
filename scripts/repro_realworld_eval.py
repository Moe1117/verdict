"""Real-world breadth eval — run the extraction + deterministic identity gates over REAL open-access
Methods sections (Europe PMC), and report DESCRIPTIVE coverage + a string-verifiable catch rate +
a false-flag rate. This is the honest external-validity companion to the synthetic stress test's 92%:
the 92% injects register line names into templated sentences; this runs on Methods sections real labs
actually wrote and published.

Honesty guardrails (see SUBMISSION.md "honest scorecard"):
  * NOT a recall % against a hand-labeled gold — that needs per-paper resource annotation (roadmap).
    The reported numbers are descriptive (resources/paper, verdict mix) plus two *verifiable* rates.
  * POSITIVE stratum denominator is STRING-VERIFIABLE: only papers whose FED Methods text literally
    contains a known register line count toward "caught X / Y" — a full-text search hit is not enough.
  * CLEAN stratum = papers using the famous-legit line HeLa but NONE of the contaminated lines (an
    EPMC NOT-query) — the deterministic gate should never FAIL one; a FAIL is a candidate false alarm
    (dumped with its flagged item so it can be adjudicated, not silently counted).
  * Lines are section-scoped via EPMC `METHODS:"..."`, and only lines actually on the register are used.

Run:  PYTHONPATH=. .venv/bin/python scripts/repro_realworld_eval.py   (writes benchmark/repro/realworld_eval.json)
Env:  RW_PER_LINE (papers per positive line, default 5), RW_CLEAN (clean papers, default 20).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from verdict.env import load_dotenv  # noqa: E402

load_dotenv()
from verdict import repro  # noqa: E402

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
OUT = os.path.join(ROOT, "benchmark/repro/realworld_eval.json")

# Famous, low-collision ICLAC-register misidentified lines. "KB" (=kilobase) and "WISH" (=the English
# word "wish") are deliberately EXCLUDED: their names string-match non-cell-line text throughout
# Methods prose and would poison the string-verifiable gold denominator with mentions that are not the
# cell line at all (verified: every "WISH"-verifiable hit was a bioinformatics/review paper with no
# cell culture). Same specificity-over-completeness rationale as the tool's own _GENERIC_TOKENS.
_POSITIVE_CANDIDATES = ["MDA-MB-435", "HEp-2", "INT-407", "ECV-304",
                        "Detroit 562", "TE671", "HBL-100", "L-132"]
_CLEAN_LINE = "HeLa"                         # a famous, legitimate line for the specificity stratum
_PER_LINE = int(os.getenv("RW_PER_LINE", "5"))
_CLEAN_N = int(os.getenv("RW_CLEAN", "20"))
_MAX_METHODS_CHARS = 9000                    # cap fed text to bound extraction cost


def _get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "methods-verifier-eval/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return r.read().decode("utf-8", "replace")


def _search(query: str, n: int) -> list[tuple]:
    url = f"{EPMC}/search?query={urllib.parse.quote(query)}&format=json&pageSize={n}&sort=CITED%20desc"
    try:
        d = json.loads(_get(url))
    except Exception:  # noqa: BLE001
        return []
    return [(r.get("pmcid"), r.get("pmid"), (r.get("title") or "")[:80])
            for r in d.get("resultList", {}).get("result", []) if r.get("pmcid")]


def search_positive(line: str, n: int) -> list[tuple]:
    # section-scoped: the line must appear in the METHODS section, not merely somewhere in the paper
    return _search(f'METHODS:"{line}" AND OPEN_ACCESS:Y AND IN_EPMC:Y AND HAS_FT:Y', n)


def search_clean(n: int) -> list[tuple]:
    excl = " ".join(f'NOT METHODS:"{l}"' for l in _POSITIVE_CANDIDATES)
    return _search(f'METHODS:"{_CLEAN_LINE}" AND OPEN_ACCESS:Y AND IN_EPMC:Y AND HAS_FT:Y {excl}', n)


def fetch_methods(pmcid: str) -> tuple[str, int]:
    """Return (methods_text, whole_body_chars). Isolate the Methods by section TITLE (robust across the
    inconsistent sec-type attribute); fall back to the whole body only if no Methods section is found."""
    try:
        xml = _get(f"{EPMC}/{pmcid}/fullTextXML")
    except Exception:  # noqa: BLE001
        return "", 0
    if len(xml) < 500:
        return "", 0
    blocks = []
    for m in re.finditer(r"<sec\b[^>]*>(.*?)</sec>", xml, re.S | re.I):
        inner = m.group(1)
        t = re.search(r"<title>(.*?)</title>", inner, re.S | re.I)
        title = re.sub(r"<[^>]+>", " ", t.group(1)).strip().lower() if t else ""
        if re.search(r"method|materials|experimental procedure", title):
            txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
            if len(txt) > 200:
                blocks.append(txt)
    body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()
    methods = " ".join(blocks) if blocks else body
    return methods[:_MAX_METHODS_CHARS], len(body)


def _sq(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def run_paper(stratum: str, pmcid: str, pmid: str, title: str, probe_line: str) -> dict:
    methods, blen = fetch_methods(pmcid)
    if not methods:
        return {"stratum": stratum, "pmcid": pmcid, "outcome": "NO_FT"}
    line_in = bool(probe_line) and _sq(probe_line) in _sq(methods)
    try:
        res = repro.extract_resources(methods)          # the ONE paid Claude call per paper
    except Exception as e:  # noqa: BLE001
        return {"stratum": stratum, "pmcid": pmcid, "outcome": f"ERR:{type(e).__name__}"}
    cell_findings = [repro.check_cell_line(cl.get("name", ""), cl.get("evidence", ""))
                     for cl in res.get("cell_lines", [])]
    fails = [{"item": f.item, "citation": f.citation} for f in cell_findings if f.result == "FAIL"]
    n_ab = len(res.get("antibodies", []) or [])
    n_sw = len(res.get("software", []) or [])
    n_res = len(cell_findings) + n_ab + n_sw
    return {"stratum": stratum, "pmcid": pmcid, "pmid": pmid, "probe_line": probe_line,
            "probe_line_in_methods": line_in, "methods_chars": len(methods), "body_chars": blen,
            "n_cells": len(cell_findings), "n_antibodies": n_ab, "n_software": n_sw,
            "n_resources": n_res, "cell_fails": fails, "title": title, "outcome": "ok"}


def main() -> None:
    pos_lines = [l for l in _POSITIVE_CANDIDATES if repro.check_cell_line(l).result == "FAIL"]
    print(f"register-confirmed positive lines: {pos_lines}", flush=True)
    jobs, seen = [], set()
    for ln in pos_lines:
        for pmcid, pmid, title in search_positive(ln, _PER_LINE):
            if pmcid not in seen:
                seen.add(pmcid)
                jobs.append(("positive", pmcid, pmid, title, ln))
    for pmcid, pmid, title in search_clean(_CLEAN_N):
        if pmcid not in seen:
            seen.add(pmcid)
            jobs.append(("clean", pmcid, pmid, title, ""))
    print(f"processing {len(jobs)} real OA papers (threaded)...", flush=True)

    rows = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(run_paper, *j) for j in jobs]
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            print(f"  [{r['stratum']:8}] {str(r.get('pmcid')):12} {r.get('outcome'):9} "
                  f"res={r.get('n_resources', '-')} fails={[f['citation'] for f in r.get('cell_fails', [])] or '-'} "
                  f"line_in_methods={r.get('probe_line_in_methods', '-')}", flush=True)

    ok = [r for r in rows if r.get("outcome") == "ok"]
    pos = [r for r in ok if r["stratum"] == "positive"]
    clean = [r for r in ok if r["stratum"] == "clean"]
    pos_verifiable = [r for r in pos if r["probe_line_in_methods"]]   # string-verifiable gold subset
    caught = [r for r in pos_verifiable if r["cell_fails"]]
    false_flags = [r for r in clean if r["cell_fails"]]
    tot_res = sum(r["n_resources"] for r in ok)
    summary = {
        "papers_processed": len(ok),
        "papers_no_fulltext": sum(1 for r in rows if r.get("outcome") == "NO_FT"),
        "papers_error": sum(1 for r in rows if str(r.get("outcome", "")).startswith("ERR")),
        "total_resources_extracted": tot_res,
        "mean_resources_per_paper": round(tot_res / len(ok), 2) if ok else 0.0,
        "positive_papers": len(pos),
        "positive_verifiable": len(pos_verifiable),
        "contaminated_lines_caught": len(caught),
        "catch_rate_on_verifiable": round(len(caught) / len(pos_verifiable), 3) if pos_verifiable else None,
        "clean_papers": len(clean),
        "false_flags_on_clean": len(false_flags),
        "false_flag_details": [{"pmcid": r["pmcid"], "fails": r["cell_fails"]} for r in false_flags],
        "lines_used": pos_lines,
    }
    print("\n=== REAL-WORLD BREADTH SUMMARY ===")
    print(json.dumps(summary, indent=1))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"summary": summary, "rows": rows}, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
