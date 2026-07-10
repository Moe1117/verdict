"""Build the frozen demo deck: run review() once per input case, save the ranked cards.
Run manually with a real key: PYTHONPATH=. .venv/bin/python scripts/build_trialdeck.py"""
import json
import glob
import os

from verdict.env import load_dotenv

load_dotenv()

from verdict import trialmatch  # noqa: E402  (import after load_dotenv so the key is set)

for inp in sorted(glob.glob("benchmark/trialdeck/inputs/*.json")):
    case = json.load(open(inp))
    cards = trialmatch.review(case["note"], condition=case.get("condition"))
    out = os.path.join("benchmark/trialdeck", os.path.basename(inp))
    json.dump(
        {"note": case["note"], "cards": [trialmatch.card_to_dict(c) for c in cards]},
        open(out, "w"),
        indent=2,
    )
    print("wrote", out, "-", len(cards), "trials")
