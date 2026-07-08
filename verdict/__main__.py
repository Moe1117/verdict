"""CLI entry point (stub). Full pipeline wiring lands next."""
from __future__ import annotations

import sys

from . import DISCLAIMER, __version__


def main() -> int:
    print(f"Verdict v{__version__}")
    print(DISCLAIMER)
    if len(sys.argv) < 2:
        print('\nusage: python -m verdict "your biomedical efficacy claim"')
        return 0
    claim = " ".join(sys.argv[1:])
    print(f'\nclaim: {claim!r}')
    print("pipeline not wired yet — see verdict/verdict.py evaluate() and the gate engine in verdict/gates.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
