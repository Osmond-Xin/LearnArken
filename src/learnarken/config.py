"""MiniMax chat configuration (Day 5, docs/specs/day5.md decision 2).

Hardened per red-team day4 #7 (the retired loader's cwd-`.env` poisoning
finding), applied from the start this time:

- only the **repo-root** `.env` is read — never `Path.cwd()`, so running
  `learnarken` from an untrusted directory cannot swap the endpoint;
- only `MINIMAX_*` keys are accepted (allowlist);
- the API URL must be https (a poisoned plain-http endpoint would leak the
  Bearer key and proxy token in cleartext).

Missing or invalid config raises — the answer path fails closed (INV-4),
it never silently degrades.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_REQUIRED = (
    "MINIMAX_API_URL",
    "MINIMAX_MODEL_NAME",
    "MINIMAX_API_KEY",
    "MINIMAX_API_PROXY_TOKEN",
)
_LINE = re.compile(r"^(MINIMAX_[A-Z0-9_]+)\s*=\s*(.*)$")


class ConfigError(RuntimeError):
    """Config missing or unsafe. Callers must not proceed (INV-4)."""


def load_minimax_config(env_path: Path | None = None) -> dict[str, str]:
    path = env_path or (REPO_ROOT / ".env")
    if not path.is_file():
        raise ConfigError(
            f"no {path.name} at the repo root — the MiniMax chat config is required "
            "for `learnarken query` (fail closed; see docs/local-services.md)"
        )
    config: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _LINE.match(line.strip())
        if match:  # non-MINIMAX keys are ignored by design (allowlist)
            config[match.group(1)] = match.group(2).strip().strip('"').strip("'")
    missing = [k for k in _REQUIRED if not config.get(k)]
    if missing:
        raise ConfigError(f"missing MiniMax config key(s): {missing} (fail closed)")
    if not config["MINIMAX_API_URL"].startswith("https://"):
        raise ConfigError("MINIMAX_API_URL must be https (fail closed)")
    return config
