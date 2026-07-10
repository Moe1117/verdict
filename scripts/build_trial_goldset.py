"""Build a small, balanced validation gold set from the TREC 2022 Clinical Trials track.

Ground truth is the track's physician relevance judgments (qrels): for each (patient topic,
trial) pair, 0 = not relevant, 1 = excluded (has the condition but an exclusion criterion makes
them ineligible), 2 = eligible (meets inclusion AND exclusion). These labels are INDEPENDENT of
this project — the whole point of the harness is to score our verdicts against judgments we did
not author. See benchmark/trialval/PROVENANCE.md for the sources and licence.

Usage (one-time; needs the two TREC files downloaded — see PROVENANCE.md):
    PYTHONPATH=. .venv/bin/python scripts/build_trial_goldset.py \
        --topics /path/to/topics2022.xml --qrels /path/to/qrels2022.txt

Writes benchmark/trialval/goldset.json. NCTs are verified to still resolve on ClinicalTrials.gov
with non-trivial eligibility text, so a downstream run never scores a dead trial.
"""
import argparse
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

from verdict import trials as _trials

# topics chosen for condition diversity; each has plenty of both eligible and excluded judgments.
TOPICS = [1, 2, 4, 5, 6, 9]
PER_LABEL = 2          # keep this many eligible + this many excluded per topic
CANDIDATES = 6         # verify up to this many candidates per (topic,label) to find resolving NCTs
_MIN_ELIG_LEN = 200    # skip trials whose eligibility text is too thin to extract criteria from


def parse_topics(path: str) -> dict[int, str]:
    root = ET.parse(path).getroot()
    out = {}
    for t in root.findall("topic"):
        out[int(t.get("number"))] = re.sub(r"\s+", " ", (t.text or "").strip())
    return out


def parse_qrels(path: str) -> dict[int, dict[str, list[str]]]:
    by_topic: dict[int, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for line in open(path):
        topic, _, nct, label = line.split()
        by_topic[int(topic)][label].append(nct)
    return by_topic


def _resolves(nct: str) -> bool:
    try:
        elig = _trials.get_eligibility(nct)
        return bool(elig.text) and len(elig.text) >= _MIN_ELIG_LEN
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", required=True)
    ap.add_argument("--qrels", required=True)
    ap.add_argument("--out", default="benchmark/trialval/goldset.json")
    args = ap.parse_args()

    topics = parse_topics(args.topics)
    qrels = parse_qrels(args.qrels)
    gold: list[dict] = []

    for tid in TOPICS:
        note = topics[tid]
        for label, name in (("2", "eligible"), ("1", "excluded")):
            kept = 0
            # sorted() makes candidate selection deterministic (no RNG), so the set is reproducible.
            for nct in sorted(qrels[tid][label])[:CANDIDATES]:
                if kept >= PER_LABEL:
                    break
                if _resolves(nct):
                    gold.append({"topic_id": tid, "note": note, "nct_id": nct, "gold": name})
                    kept += 1
            print(f"topic {tid} {name}: kept {kept}/{PER_LABEL}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(gold, open(args.out, "w"), indent=2)
    n_e = sum(1 for g in gold if g["gold"] == "eligible")
    n_x = sum(1 for g in gold if g["gold"] == "excluded")
    print(f"\nwrote {args.out}: {len(gold)} pairs ({n_e} eligible, {n_x} excluded)")


if __name__ == "__main__":
    main()
