"""End-to-end STRESS TEST of the verification layer — the honest 'does the tool actually work' number.

The register lookup is deterministic (100% by construction). The real tool must survive the messy
world: Claude has to EXTRACT the cell-line name from realistic Methods prose before the lookup can
fire. This measures the full pipeline (extract -> match -> verdict) on known-contaminated lines
embedded in varied/adversarial phrasing, and diagnoses every miss:
  - extraction_miss : the name was never pulled from the prose (the silent-failure risk)
  - match_miss      : extracted, but the register lookup didn't fire (name-matching gap)
Also a false-positive probe: legit lines in Methods should NOT be flagged. Run:
  PYTHONPATH=. .venv/bin/python scripts/repro_stress_test.py [n_lines]
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from verdict.env import load_dotenv

load_dotenv()
from verdict import repro  # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def primary(name: str) -> str:
    return re.sub(r"\(.*?\)", "", name).strip()


def short_tissue(claimed: str) -> str:
    t = (claimed or "").lower()
    for k in ["carcinoma", "melanoma", "glioblastoma", "leukemia", "leukaemia", "lymphoma",
              "adenocarcinoma", "sarcoma", "breast", "lung", "colon", "prostate", "ovarian",
              "pancreatic", "bladder", "cervical", "liver", "thyroid", "kidney", "brain"]:
        if k in t:
            return k
    return "tumour"


# realistic-to-nasty Methods phrasings; {L}=line name, {T}=tissue descriptor
TEMPLATES = [
    ("plain", "The {L} cell line was used in this study."),
    ("cells", "{L} cells were maintained in DMEM supplemented with 10% FBS at 37C."),
    ("descriptor", "Experiments used the {L} {T} line, cultured under standard conditions."),
    ("vendor", "The {L} line was obtained from the cell bank and authenticated by the supplier."),
    ("list", "The cell lines used were {L}, A549, and HEK293, all grown to 80% confluence."),
    ("passing", "Following established protocols, gene knockdowns were performed in {L} and validated "
                "by qPCR; culture conditions followed the recommendations for this line."),
    ("parenthetical", "Adherent cultures (line {L}; {T}) were passaged twice weekly and used below passage 20."),
    ("dense", "To model progression, {L}-derived orthotopic xenografts were established in athymic nude "
              "mice and tumour growth was monitored over eight weeks by caliper measurement."),
    ("nospace", "The {Lns} cell line was used for all in vitro assays."),  # hyphen/space stripped
]


def build_snippet(line: str, tissue: str, tmpl: str) -> str:
    return tmpl.replace("{L}", line).replace("{T}", tissue).replace("{Lns}", line.replace("-", "").replace(" ", ""))


def target_finding(rep, line: str):
    for f in rep.findings:
        if f.kind != "cell_line":
            continue
        nm = f.item.replace("cell line:", "").strip()
        if repro._squash(line) and repro._squash(line) in repro._squash(nm) or norm(line) in norm(nm):
            return f
    return None


# ---- build the misidentified test set ----
seen, mis = set(), []
for rec in repro._load_iclac().values():
    if rec["iclac_id"] in seen:
        continue
    if not rec["true_identity"] or rec["true_identity"].lower() in ("unknown", ""):
        continue
    seen.add(rec["iclac_id"])
    mis.append((primary(rec["name"]), rec))
mis.sort(key=lambda x: x[1]["iclac_id"])
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
step = max(1, len(mis) // N)
sample = [mis[i] for i in range(0, len(mis), step)][:N]

# one snippet per line, cycling templates so every phrasing is exercised
cases = []
for i, (line, rec) in enumerate(sample):
    tname, tmpl = TEMPLATES[i % len(TEMPLATES)]
    cases.append(("mis", line, rec, tname, build_snippet(line, short_tissue(rec["claimed_origin"]), tmpl)))

# false-positive probe: legit lines in the same phrasings
LEGIT = ["HeLa", "MCF-7", "HEK293", "A549", "U-251 MG", "Jurkat", "K-562", "PC-3", "HepG2",
         "SH-SY5Y", "Caco-2", "HT-29", "DU145", "LNCaP", "SK-BR-3", "THP-1", "U2OS", "A431"]
legit = [n for n in LEGIT if repro.check_cell_line(n).result == "PASS"]
for i, line in enumerate(legit):
    tname, tmpl = TEMPLATES[i % (len(TEMPLATES) - 1)]  # skip nospace for legit
    cases.append(("legit", line, None, tname, build_snippet(line, "cancer", tmpl)))

print(f"stress-testing {len(sample)} misidentified + {len(legit)} legit lines through the full pipeline...\n")


def run(case):
    kind, line, rec, tname, snippet = case
    try:
        rep = repro.review(snippet)
    except Exception as e:  # noqa: BLE001
        return {"kind": kind, "line": line, "template": tname, "outcome": f"ERROR:{type(e).__name__}"}
    f = target_finding(rep, line)
    if kind == "mis":
        if f is None:
            outcome = "extraction_miss"
        elif f.result == "FAIL":
            outcome = "caught"
        else:
            outcome = "match_miss"
        return {"kind": kind, "line": line, "template": tname, "true": rec["true_identity"], "outcome": outcome}
    # legit: any cell_line FAIL is a false positive
    fp = any(x.kind == "cell_line" and x.result == "FAIL" for x in rep.findings)
    return {"kind": kind, "line": line, "template": tname, "outcome": "false_flag" if fp else "clean"}


rows = []
with ThreadPoolExecutor(max_workers=8) as ex:
    for fut in as_completed([ex.submit(run, c) for c in cases]):
        rows.append(fut.result())

mis_rows = [r for r in rows if r["kind"] == "mis"]
leg_rows = [r for r in rows if r["kind"] == "legit"]
caught = sum(1 for r in mis_rows if r["outcome"] == "caught")
ext_miss = sum(1 for r in mis_rows if r["outcome"] == "extraction_miss")
match_miss = sum(1 for r in mis_rows if r["outcome"] == "match_miss")
false_flags = sum(1 for r in leg_rows if r["outcome"] == "false_flag")

# per-template catch breakdown
by_t = {}
for r in mis_rows:
    by_t.setdefault(r["template"], [0, 0])
    by_t[r["template"]][1] += 1
    if r["outcome"] == "caught":
        by_t[r["template"]][0] += 1

summary = {
    "n_misidentified": len(mis_rows), "n_legit": len(leg_rows),
    "end_to_end_catch_rate": round(caught / (len(mis_rows) or 1), 3),
    "caught": caught, "extraction_miss": ext_miss, "match_miss": match_miss,
    "false_flags_legit": false_flags,
    "by_template": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_t.items())},
}
json.dump({"summary": summary, "rows": rows}, open("benchmark/repro/stress_eval.json", "w"), indent=1)
print("misses (for diagnosis):")
for r in mis_rows:
    if r["outcome"] not in ("caught",):
        print(f"  [{r['outcome']:16}] {r['line']:16} ({r['template']}) true={r.get('true','')}")
for r in leg_rows:
    if r["outcome"] == "false_flag":
        print(f"  [FALSE-FLAG      ] {r['line']} ({r['template']})")
print(f"\n=== END-TO-END STRESS TEST (full pipeline, realistic + adversarial phrasing) ===")
print(f"  catch rate on contaminated lines : {summary['end_to_end_catch_rate']:.0%}  "
      f"({caught}/{len(mis_rows)})")
print(f"  misses: extraction {ext_miss} · name-match {match_miss}")
print(f"  false-flags on legit lines       : {false_flags}/{len(leg_rows)}")
print(f"  per-phrasing catch: {summary['by_template']}")
