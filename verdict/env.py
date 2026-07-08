"""A tiny, dependency-free .env loader for the CLI.

Deliberately minimal: KEY=VALUE per line, `#` comments and blanks ignored, a leading
`export ` tolerated, surrounding single/double quotes stripped, empty values skipped. It
NEVER overrides a variable already present in the real environment — an exported key always
wins over the file. Missing file is a no-op. (No python-dotenv dependency.)
"""
from __future__ import annotations

import os


def load_dotenv(path: str = ".env") -> None:
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key or not value or key in os.environ:
                continue
            os.environ[key] = value
