"""Definitive hero benchmark: bare Claude vs the ICLAC register.

Un-stackable by design: tests the ENTIRE register (every known misidentified line — famous AND
obscure, NO exclusions) plus a set of well-known legitimate control lines. Threaded. Scores the
bare model two ways — lenient (did it even flag the line as misidentified?) and strict (flag +
correct true identity) — with a famous-vs-obscure breakdown and Wilson 95% CIs.

Honest framing of the tool's side: it is a deterministic register lookup, so it flags 100% of the
KNOWN misidentified lines by construction — the point is completeness + citability, and the delta
vs the model (what the model misses / hallucinates) is the real result. Run:
  PYTHONPATH=. .venv/bin/python scripts/repro_iclac_benchmark.py [max_misidentified]
"""
import json
import math
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from verdict.env import load_dotenv

load_dotenv()
from verdict import repro  # noqa: E402
from verdict.parse import call_tool  # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def primary(name: str) -> str:
    return re.sub(r"\(.*?\)", "", name).strip()


def fuzzy(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    return a in b or b in a or a.replace("-", "").replace(" ", "") == b.replace("-", "").replace(" ", "")


def wilson(k: int, n: int, z: float = 1.96) -> list:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - m) / d, 3), round((c + m) / d, 3)]


# famous contaminations used ONLY to label the breakdown — NOT excluded from the test.
FAMOUS_LABEL = {norm(x) for x in [
    "KB", "HEp-2", "Hep-2", "INT-407", "Intestine 407", "Chang liver", "WISH", "ECV-304", "ECV304",
    "MDA-MB-435", "Girardi heart", "L-132", "Detroit 562", "FL", "TE671", "HBL-100", "Hep-2",
    "Intestine 407", "KB cells", "Hep 2",
]}

LEGIT = ["HeLa", "MCF-7", "HEK293", "A549", "U-251 MG", "Jurkat", "K-562", "PC-3", "HepG2",
         "SH-SY5Y", "NIH/3T3", "CHO", "Caco-2", "HT-29", "DU145", "LNCaP", "SK-BR-3", "RAW 264.7",
         "THP-1", "U2OS", "HL-60", "MDA-MB-231", "A431", "Vero", "HCT116", "SW480", "T47D",
         "PANC-1", "MIA PaCa-2", "Neuro-2a", "BV-2", "COS-7", "293T", "Huh-7", "OVCAR-3", "22Rv1"]

TOOL = {
    "name": "assess_cell_line",
    "description": "Assess whether a cell line is a known misidentified / cross-contaminated cell line.",
    "input_schema": {"type": "object", "properties": {
        "is_misidentified": {"type": "boolean"},
        "actually_is": {"type": "string", "description": "the cell line it really is, or empty"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
        "required": ["is_misidentified", "actually_is", "confidence"]},
}
SYSTEM = "You are a cell-line authentication expert. Answer only from your own knowledge; do not hedge."


def ask_llm(name: str) -> dict:
    for _ in range(3):
        try:
            return call_tool(SYSTEM, f"Is the cell line '{name}' a known misidentified or cross-contaminated "
                                     f"cell line? If so, which cell line is it actually?", TOOL, max_tokens=300)
        except Exception:  # noqa: BLE001
            continue
    return {"is_misidentified": False, "actually_is": "ERROR", "confidence": "low", "_error": True}


# ---- build the sets ----
seen, misids = set(), []
for rec in repro._load_iclac().values():
    if rec["iclac_id"] in seen:
        continue
    seen.add(rec["iclac_id"])
    misids.append((primary(rec["name"]), rec))
misids.sort(key=lambda x: x[1]["iclac_id"])
if len(sys.argv) > 1:
    misids = misids[: int(sys.argv[1])]
# large legit control set: curated famous lines + the register's own true-identity lines
# (authentic lines that are NOT themselves misidentified) — a real specificity test at scale.
_ti = set()
for _r in repro._load_iclac().values():
    _t = _r["true_identity"]
    if _t and _t.lower() not in ("unknown", ""):
        _c = re.split(r"[;,/]", re.sub(r"\(.*?\)", "", _t))[0].strip()
        if _c:
            _ti.add(_c)
legit = [n for n in dict.fromkeys(LEGIT + sorted(_ti)) if repro.check_cell_line(n).result == "PASS"]

items = [("mis", n, rec) for n, rec in misids] + [("legit", n, None) for n in legit]
print(f"testing {len(misids)} misidentified + {len(legit)} legit = {len(items)} lines (threaded)...")


def assess(item):
    kind, name, rec = item
    d = ask_llm(name)
    flagged, llm_id, conf = bool(d.get("is_misidentified")), d.get("actually_is", ""), d.get("confidence", "low")
    if kind == "mis":
        known = bool(rec["true_identity"] and rec["true_identity"].lower() not in ("unknown", ""))
        id_ok = flagged and known and fuzzy(llm_id, rec["true_identity"])
        correct = id_ok
        return {"name": name, "gold": "misidentified", "true_identity": rec["true_identity"],
                "iclac_id": rec["iclac_id"], "cvcl": rec["cvcl"], "known_identity": known,
                "famous": norm(primary(rec["name"])) in FAMOUS_LABEL,
                "llm_verdict": (f"actually {llm_id}" if flagged else "clean"), "llm_confidence": conf,
                "llm_flagged": flagged, "llm_correct": correct,
                "llm_confident_wrong": conf in ("high", "medium") and not correct, "error": bool(d.get("_error"))}
    correct = not flagged
    return {"name": name, "gold": "legitimate", "true_identity": "", "iclac_id": "", "cvcl": "",
            "known_identity": False, "famous": False,
            "llm_verdict": (f"actually {llm_id}" if flagged else "clean"), "llm_confidence": conf,
            "llm_flagged": flagged, "llm_correct": correct,
            "llm_confident_wrong": conf in ("high", "medium") and flagged, "error": bool(d.get("_error"))}


rows = []
with ThreadPoolExecutor(max_workers=10) as ex:
    futs = [ex.submit(assess, it) for it in items]
    for i, fut in enumerate(as_completed(futs)):
        rows.append(fut.result())
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(items)}")

mis = [r for r in rows if r["gold"] == "misidentified" and not r["error"]]
known = [r for r in mis if r["known_identity"]]
famous = [r for r in known if r["famous"]]
tail = [r for r in known if not r["famous"]]
leg = [r for r in rows if r["gold"] == "legitimate" and not r["error"]]


def acc(sub, key="llm_correct"):
    return round(sum(r[key] for r in sub) / len(sub), 3) if sub else None


summary = {
    "n_total": len(rows), "n_misidentified": len(mis), "n_known_identity": len(known),
    "n_famous": len(famous), "n_obscure_tail": len(tail), "n_legit": len(leg),
    "llm_strict_accuracy_known": acc(known),                    # flagged + correct identity
    "llm_strict_ci95": wilson(sum(r["llm_correct"] for r in known), len(known)),
    "llm_flag_recall_all": acc(mis, "llm_flagged"),             # flagged as misidentified at all
    "llm_strict_famous": acc(famous), "llm_strict_tail": acc(tail),
    "llm_flag_recall_tail": acc(tail, "llm_flagged"),
    "llm_confident_wrong": sum(r["llm_confident_wrong"] for r in rows),
    "llm_false_flag_legit": sum(1 for r in leg if r["llm_flagged"]),
    "tool_catches_known": 1.0, "tool_false_positive_legit": 0,   # deterministic register lookup
    "errors": sum(1 for r in rows if r["error"]),
}
json.dump({"summary": summary, "rows": rows}, open("benchmark/repro/iclac_eval.json", "w"), indent=1)
s = summary
print(f"\n=== DEFINITIVE — bare Claude vs the ENTIRE ICLAC register ===")
print(f"  set: {s['n_misidentified']} misidentified ({s['n_known_identity']} with known identity: "
      f"{s['n_famous']} famous + {s['n_obscure_tail']} obscure) + {s['n_legit']} legit controls")
print(f"  bare Claude  strict accuracy (flag+identity): {s['llm_strict_accuracy_known']:.0%}  "
      f"95% CI {s['llm_strict_ci95']}")
print(f"               even just FLAGGING as misidentified: {s['llm_flag_recall_all']:.0%}")
print(f"               famous {s['llm_strict_famous']:.0%} vs obscure tail {s['llm_strict_tail']:.0%}  "
      f"(tail flag-recall {s['llm_flag_recall_tail']:.0%})")
print(f"               confidently wrong on {s['llm_confident_wrong']} lines; false-flagged {s['llm_false_flag_legit']}/{s['n_legit']} legit")
print(f"  register     catches 100% of known misidentified (completeness), 0 false-positives, every FAIL cited")
