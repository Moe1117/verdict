"""Head-to-head harness: Methods Verifier vs a missing-RRID checker (SciScore / Rigor & Transparency
Index) on the OBSCURE TAIL of the ICLAC register — where a from-memory check is weakest and where
citability matters most.

The wedge we can measure WITHOUT external access (fully deterministic, no API): for each obscure-tail
contaminated line, does the tool (a) CATCH it, and (b) CITE its TRUE identity + CVCL — the thing a
"flag this cell line for authentication" / "missing RRID" checker structurally cannot provide.

The SciScore column requires a SciScore run. SciScore is a commercial product; we do NOT fabricate its
results. This script emits the exact Methods snippets to paste into SciScore and leaves its columns
null for a human to fill. Everything the tool column claims is reproducible here, offline.

Run:  PYTHONPATH=. .venv/bin/python scripts/repro_head_to_head.py
"""
import json
import re

from verdict import repro

# The famous ~11 lines a bare model already knows — EXCLUDED here so we test only the obscure tail.
FAMOUS = {repro._norm(x) for x in [
    "KB", "HEp-2", "Hep-2", "INT-407", "Intestine 407", "Chang liver", "WISH", "ECV-304", "ECV304",
    "MDA-MB-435", "Girardi heart", "L-132", "Detroit 562", "FL", "TE671", "HBL-100", "Hep 2",
]}


def primary(name: str) -> str:
    return re.sub(r"\(.*?\)", "", name).strip()


def build_tail_sample(n: int = 15) -> list:
    seen, tail = set(), []
    for rec in repro._load_iclac().values():
        if rec["iclac_id"] in seen:
            continue
        seen.add(rec["iclac_id"])
        name = primary(rec["name"])
        if repro._norm(name) in FAMOUS:
            continue
        if rec["true_identity"] and rec["true_identity"].lower() not in ("unknown", ""):
            tail.append((name, rec))
    tail.sort(key=lambda x: x[1]["iclac_id"])
    step = max(1, len(tail) // n)  # spread the sample deterministically across the tail
    return tail[::step][:n]


def main() -> None:
    rows = []
    for name, rec in build_tail_sample():
        methods = f"Cells were the {name} line, maintained in DMEM with 10% FBS at 37C."
        f = repro.check_cell_line(name, evidence=name)
        rows.append({
            "line": name,
            "iclac_id": rec["iclac_id"],
            "true_identity": rec["true_identity"],
            "cvcl": rec["cvcl"],
            "methods_snippet": methods,
            # --- Methods Verifier (deterministic, reproduced here) ---
            "tool_caught": f.result == "FAIL",
            "tool_cites_true_identity": bool(f.citation) and rec["cvcl"] in f.citation,
            "tool_citation": f.citation,
            # --- SciScore / RTI (RUN SciScore on methods_snippet and fill these in) ---
            "sciscore_flagged": None,               # did SciScore flag the line at all? True/False
            "sciscore_cites_true_identity": None,   # does SciScore state the TRUE identity + CVCL? (expected: False)
        })

    caught = sum(r["tool_caught"] for r in rows)
    cited = sum(r["tool_cites_true_identity"] for r in rows)
    out = {
        "n": len(rows),
        "tool_caught": caught,
        "tool_cites_true_identity": cited,
        "note": ("SciScore columns are null on purpose — SciScore is commercial; run it on each "
                 "methods_snippet and fill sciscore_flagged / sciscore_cites_true_identity. The wedge "
                 "this harness measures offline: the tool catches obscure-tail contaminated lines AND "
                 "cites their TRUE identity + CVCL, which a missing-RRID checker does not provide."),
        "rows": rows,
    }
    json.dump(out, open("benchmark/repro/head_to_head.json", "w"), indent=1)

    print(f"=== Methods Verifier vs missing-RRID checker — obscure tail (n={len(rows)}) ===\n")
    print(f"{'line':<16}{'ICLAC':<12}{'true identity':<22}{'tool: caught?':<14}{'tool: cites true id?'}")
    for r in rows:
        print(f"{r['line'][:15]:<16}{r['iclac_id']:<12}{r['true_identity'][:20]:<22}"
              f"{'FAIL✓' if r['tool_caught'] else 'missed':<14}{'yes ('+r['tool_citation']+')' if r['tool_cites_true_identity'] else 'no'}")
    print(f"\ntool caught {caught}/{len(rows)} and cited the true identity+CVCL on {cited}/{len(rows)}.")
    print("SciScore column: run SciScore on the emitted snippets (benchmark/repro/head_to_head.json) and fill it in —")
    print("SciScore flags cell lines for authentication / missing RRID but does not cite the register's true identity.")


if __name__ == "__main__":
    main()
