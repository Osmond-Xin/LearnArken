"""Local credential loading (Day 4a).

MiniMax credentials live in a git-ignored `.env` (security red line: values
never enter the repo). This loads them so the CLI works without the caller
exporting anything by hand. Deliberately minimal — our `.env` holds plain
`KEY=value` lines and nothing else.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env(path: Path | None = None) -> None:
    """Load `KEY=value` pairs from `.env` into the environment.

    Real environment variables win — this only fills in what is unset, so an
    explicit export or a test's monkeypatch is never clobbered.
    """
    candidates = [path] if path else [Path.cwd() / ".env", _REPO_ROOT / ".env"]
    for candidate in candidates:
        if candidate is None or not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return
