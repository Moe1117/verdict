"""CLI: run Verdict over the frozen demo corpora (deterministic, offline).

  python -m verdict --list              # list available frozen claims
  python -m verdict --id C08            # resolve a frozen claim by id
  python -m verdict "some claim text"   # match a frozen claim by text (else guidance)
"""
from __future__ import annotations

import sys

from . import DISCLAIMER, __version__
from .certainty import grade_certainty
from .corpora import available, load_rows
from .verdict import VerdictCard, run_frozen, run_live

_SIGN = {1: "+", -1: "-", 0: "0"}


def render_card(card: VerdictCard) -> str:
    out = [f"CLAIM: {card.claim}"]
    cert = grade_certainty(card.ledger, card.verdict)
    out += [f"VERDICT: {card.verdict.value}   ·   certainty {cert.level}", "", "gate trace:"]
    for g in card.gate_trace:
        out.append(f"  [{'ok' if g.passed else '--'}] {g.gate}: {g.detail}")
    out += ["", "evidence ledger:"]
    for r in card.ledger:
        flag = "EXCLUDED " if not r.integrity_ok else ""
        n = f"n={r.n_int}" if r.n_int else ""
        surr = " [surrogate]" if not r.outcome_match else ""
        out.append(f"  {flag}[{_SIGN.get(r.direction, '?')}] {r.source_id:16} {r.design:22} {n:9} {r.finding}{surr}")
        if not r.integrity_ok and r.integrity_note:
            out.append(f"        -> {r.integrity_note}")
    out += ["", DISCLAIMER]
    return "\n".join(out)


def _match_by_text(text: str) -> str | None:
    t = text.lower()
    for cid in available():
        meta, _ = load_rows(cid)
        if t in meta.get("claim", "").lower() or meta.get("claim", "").lower() in t:
            return cid
    return None


def main() -> int:
    print(f"Verdict v{__version__}\n")
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--list":
        ids = available()
        print("frozen claims:" if ids else "no frozen corpora yet (populate benchmark/corpora/*.json)")
        for cid in ids:
            meta, _ = load_rows(cid)
            print(f"  {cid}  {meta.get('claim', '')}")
        return 0

    if args[0] == "--id":
        if len(args) < 2:
            print("usage: python -m verdict --id C08")
            return 2
        print(render_card(run_frozen(args[1])))
        return 0

    if args[0] == "--live":
        if len(args) < 2:
            print('usage: python -m verdict --live "drug improves outcome in population"')
            return 2
        import os
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("live path needs ANTHROPIC_API_KEY (Claude parses the claim + extracts each study).")
            return 2
        print("running live: parse -> PubMed retrieval -> Claude extraction -> deterministic gates ...\n")
        print(render_card(run_live(" ".join(args[1:]))))
        return 0

    claim = " ".join(args)
    cid = _match_by_text(claim)
    if cid:
        print(render_card(run_frozen(cid)))
        return 0
    print(f"no frozen corpus matches {claim!r}.")
    print("Use --list, or run the live pipeline (needs ANTHROPIC_API_KEY + NCBI_EMAIL).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
