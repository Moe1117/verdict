#!/usr/bin/env python3
"""Fidelity gate — fail if any headline claim drifts from the committed benchmark data or the prose.

Reads benchmark/claims.json. For each claim it runs two deterministic checks:
  1. DATA  — the committed artifact's value at `path` matches `expected` within `tol`.
  2. PROSE — the claim's rendered number appears verbatim in each `appears_in` doc.

Exits non-zero on any failure. No network, no API key, no model — pure stdlib, always-on, free in CI.
This is the "prove the headline still holds on every push" gate: if someone regenerates a benchmark,
edits a number in the README, or hand-tunes `expected`, the three sources fall out of agreement and
the build goes red until a human reconciles data ↔ registry ↔ prose.

Modes:
  python scripts/check_claims.py              # the gate (used by CI)
  python scripts/check_claims.py --update      # re-baseline: rewrite each `expected` from current data
                                               #   (use after an INTENTIONAL benchmark change, then fix prose)
  python scripts/check_claims.py --overclaim   # + optional LLM pass flagging prose numbers with no registry
                                               #   entry (needs ANTHROPIC_API_KEY; skipped if absent)

Design note: mirrors the NCypher finalist's GitHub-Actions reproducibility gate (Claude re-checks the
headline on every push), but the always-on core is deterministic so it never costs a token or flakes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "benchmark" / "claims.json"


def resolve(data: object, path: str) -> object:
    """Walk a dotted path into nested dicts/lists (list indices allowed as integers)."""
    cur = data
    for key in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(key)]
        else:
            cur = cur[key]
    return cur


def rendered(claim: dict) -> str | None:
    """The exact string this claim expects to see in the prose, derived from the data-backed value."""
    if claim.get("display_rule") == "round_pct":
        return f"{round(claim['expected'] * 100)}%"
    return claim.get("display")


def load_registry() -> dict:
    return json.loads(REGISTRY.read_text())


def check(claims: list[dict]) -> list[str]:
    failures: list[str] = []
    cache: dict[Path, object] = {}
    for c in claims:
        cid = c["id"]
        src = ROOT / c["source"]
        if src not in cache:
            try:
                cache[src] = json.loads(src.read_text())
            except FileNotFoundError:
                failures.append(f"[{cid}] data: source file missing: {c['source']}")
                continue
        # 1. DATA CHECK
        try:
            actual = resolve(cache[src], c["path"])
        except (KeyError, IndexError, ValueError, TypeError) as e:
            failures.append(f"[{cid}] data: path '{c['path']}' not resolvable in {c['source']} ({e})")
            continue
        exp, tol = c["expected"], c.get("tol", 0)
        numeric = isinstance(exp, (int, float)) and not isinstance(exp, bool)
        if numeric and isinstance(actual, (int, float)) and not isinstance(actual, bool):
            if abs(actual - exp) > tol:
                failures.append(
                    f"[{cid}] data: {c['source']}:{c['path']} = {actual}, expected {exp} (tol ±{tol})"
                )
        elif actual != exp:
            failures.append(f"[{cid}] data: {c['source']}:{c['path']} = {actual!r}, expected {exp!r}")
        # 2. PROSE CHECK
        token = rendered(c)
        if token:
            for doc in c.get("appears_in", []):
                text = (ROOT / doc).read_text()
                if token not in text:
                    failures.append(
                        f"[{cid}] prose: '{token}' not found in {doc} — "
                        f"reconcile prose with the data ({c['statement']})"
                    )
    return failures


def update(reg: dict) -> None:
    """Re-baseline every `expected` from the current committed data. Prose is left for the human."""
    cache: dict[Path, object] = {}
    changed = 0
    for c in reg["claims"]:
        src = ROOT / c["source"]
        if src not in cache:
            cache[src] = json.loads(src.read_text())
        new = resolve(cache[src], c["path"])
        if new != c["expected"]:
            print(f"  {c['id']}: {c['expected']} -> {new}")
            c["expected"] = new
            changed += 1
    REGISTRY.write_text(json.dumps(reg, indent=2) + "\n")
    print(f"\nre-baselined {changed} claim(s) into {REGISTRY.relative_to(ROOT)}.")
    print("NOW reconcile the prose: any rendered number that moved must be updated in README/SUBMISSION.")


def overclaim(reg: dict) -> None:
    """Optional LLM audit: flag quantitative claims in the prose not backed by the registry.

    Opt-in and non-fatal. Skips cleanly when anthropic / ANTHROPIC_API_KEY is unavailable, so the
    always-on gate never depends on it.
    """
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n[overclaim] skipped — no ANTHROPIC_API_KEY.")
        return
    try:
        import anthropic
    except ImportError:
        print("\n[overclaim] skipped — anthropic SDK not installed.")
        return
    backed = "\n".join(f"- {c['statement']} ({rendered(c) or c['expected']})" for c in reg["claims"])
    prose = "\n\n".join(
        f"===== {d} =====\n{(ROOT / d).read_text()}"
        for d in ("README.md", "SUBMISSION.md")
        if (ROOT / d).exists()
    )
    msg = (
        "You audit a scientific tool's docs for OVERCLAIMING. Below are the ONLY quantitative claims "
        "backed by committed benchmark data, then the full prose. List every quantitative/empirical "
        "claim in the prose that is NOT backed by the list or that contradicts it. Reply with a terse "
        "bullet list, or 'NONE'.\n\n=== BACKED CLAIMS ===\n" + backed + "\n\n=== PROSE ===\n" + prose
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-opus-4-8", max_tokens=1024, messages=[{"role": "user", "content": msg}]
    )
    print("\n[overclaim] LLM audit (advisory, non-fatal):\n" + resp.content[0].text)


def main() -> int:
    reg = load_registry()
    claims = reg["claims"]

    if "--update" in sys.argv:
        update(reg)
        return 0

    failures = check(claims)
    n = len(claims)
    if failures:
        print(f"FIDELITY GATE: FAIL — {len(failures)} issue(s) across {n} claim(s)\n")
        for f in failures:
            print("  ✗ " + f)
        print(
            "\nEvery headline number must agree across data (benchmark/*.json), registry "
            "(benchmark/claims.json), and prose (README/SUBMISSION). Fix the divergence, or re-baseline "
            "an intentional change with:  python scripts/check_claims.py --update"
        )
        return 1

    print(f"FIDELITY GATE: PASS — {n}/{n} claims reconcile (data ↔ registry ↔ prose).")
    for c in claims:
        tok = rendered(c)
        loc = f"{Path(c['source']).name}:{c['path']}"
        print(f"  ✓ {c['id']:<24} {loc:<48} = {c['expected']}" + (f"  → '{tok}'" if tok else ""))

    if "--overclaim" in sys.argv:
        overclaim(reg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
