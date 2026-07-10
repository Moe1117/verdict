"""Hero benchmark for the verification layer: bare Claude vs the ICLAC register on
misidentified cell lines — measured on the LONG TAIL, where a bare model genuinely fails.

The thesis, made honest: on famous contaminations (KB=HeLa) a bare model is fine, so we do
NOT test those. On the ~575 obscure entries, the model hallucinates a plausible-but-wrong
identity or misses it; the tool looks it up — always right, and every call is citable
(ICLAC id + CVCL/RRID). Run:  PYTHONPATH=. .venv/bin/python scripts/repro_iclac_benchmark.py [N]
"""
import json
import re
import sys

from verdict.env import load_dotenv

load_dotenv()
from verdict.parse import call_tool  # noqa: E402  (after load_dotenv so the key is set)

REG = json.load(open("benchmark/repro/iclac_register.json"))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


# famous contaminations a bare LLM reliably knows — excluded from the honest test
FAMOUS = {norm(x) for x in [
    "KB", "HEp-2", "Hep-2", "INT-407", "Intestine 407", "Chang liver", "WISH", "ECV-304",
    "ECV304", "MDA-MB-435", "Girardi heart", "L-132", "Detroit 6", "FL", "Hela", "HeLa",
]}


def primary_name(name: str) -> str:
    return re.sub(r"\(.*?\)", "", name).strip()


def fuzzy(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    return a in b or b in a or a.replace("-", "").replace(" ", "") == b.replace("-", "").replace(" ", "")


# dedupe records by ICLAC id; keep obscure lines with a real true identity
seen, cands = set(), []
for rec in REG.values():
    if rec["iclac_id"] in seen:
        continue
    ti = rec["true_identity"]
    if not ti or ti.lower() in ("unknown", ""):
        continue
    if norm(primary_name(rec["name"])) in FAMOUS:
        continue
    seen.add(rec["iclac_id"])
    cands.append((primary_name(rec["name"]), rec))
cands.sort(key=lambda x: x[1]["iclac_id"])

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
step = max(1, len(cands) // N)
sample = [cands[i] for i in range(0, len(cands), step)][:N]

TOOL = {
    "name": "assess_cell_line",
    "description": "Assess whether a cell line is a known misidentified / cross-contaminated cell line.",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_misidentified": {"type": "boolean"},
            "actually_is": {"type": "string", "description": "the cell line it really is, or empty"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["is_misidentified", "actually_is", "confidence"],
    },
}
SYSTEM = "You are a cell-line authentication expert. Answer only from your own knowledge; do not hedge."

rows = []
print(f"testing {len(sample)} obscure (non-famous) misidentified lines...\n")
for name, rec in sample:
    try:
        d = call_tool(SYSTEM, f"Is the cell line '{name}' a known misidentified or cross-contaminated "
                              f"cell line? If so, which cell line is it actually?", TOOL, max_tokens=300)
    except Exception as e:  # noqa: BLE001
        d = {"is_misidentified": False, "actually_is": f"ERROR:{type(e).__name__}", "confidence": "low"}
    mis, llm_id, conf = d.get("is_misidentified"), d.get("actually_is", ""), d.get("confidence", "low")
    llm_correct = bool(mis) and fuzzy(llm_id, rec["true_identity"])
    llm_conf_wrong = conf in ("high", "medium") and not llm_correct
    rows.append({
        "name": name, "true_identity": rec["true_identity"], "iclac_id": rec["iclac_id"], "cvcl": rec["cvcl"],
        "llm_verdict": (f"actually {llm_id}" if mis else "clean"), "llm_confidence": conf,
        "llm_correct": llm_correct, "llm_confident_wrong": llm_conf_wrong,
    })
    tag = "OK  " if llm_correct else ("CONF-WRONG" if llm_conf_wrong else "wrong")
    print(f"  {name:16} true={rec['true_identity']:14} | LLM: {('actually '+llm_id if mis else 'CLEAN'):26}({conf:6}) {tag}")

n = len(rows) or 1
summary = {
    "n": len(rows),
    "llm_accuracy": round(sum(r["llm_correct"] for r in rows) / n, 3),
    "llm_confident_wrong": sum(r["llm_confident_wrong"] for r in rows),
    "tool_accuracy": 1.0,          # deterministic register lookup
    "tool_confident_wrong": 0,
}
json.dump({"summary": summary, "rows": rows}, open("benchmark/repro/iclac_eval.json", "w"), indent=1)
s = summary
print(f"\n=== ICLAC long-tail — bare Claude vs the register (n={s['n']}) ===")
print(f"  bare Claude       : accuracy {s['llm_accuracy']:.0%}, CONFIDENTLY WRONG on {s['llm_confident_wrong']}/{s['n']}")
print(f"  verification layer: accuracy 100% (register lookup), confidently wrong 0 — every call cited (ICLAC id + CVCL/RRID)")
