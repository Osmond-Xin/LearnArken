"""MiniMax chat configuration (Day 5, docs/specs/day5.md decision 2).

Hardened per red-team day4 #7 (the retired loader's cwd-`.env` poisoning
finding), applied from the start this time:

- only the **repo-root** `.env` is read — never `Path.cwd()`, so running
  `learnarken` from an untrusted directory cannot swap the endpoint;
- only `MINIMAX_*` keys are accepted (allowlist);
- the API URL must be https (a poisoned plain-http endpoint would leak the
  Bearer key and proxy token in cleartext) **unless it addresses loopback**,
  where there is no wire to intercept — see the endpoint policy below.

Missing or invalid config raises — the answer path fails closed (INV-4),
it never silently degrades.

## Endpoint policy (2026-07-25, red-team `readme-refactor-2026-07-25` F-02)

The generation endpoint is OpenAI-compatible, so any local server that speaks
`/chat/completions` (llama.cpp `llama-server`, vLLM, Ollama, TGI) is a drop-in
replacement for the remote provider. Until now it was **not** actually
swappable: the https-only rule rejected exactly the URL shape every local
server has (`http://127.0.0.1:PORT/v1`), so "data never leaves the machine" was
unreachable by configuration, not merely unconfigured. Two rules replace it:

1. **`https` for anything off-box; plaintext only on loopback.** The host is
   parsed, never prefix-matched, so `http://127.0.0.1@evil.example/v1` and
   `http://localhost.evil.example/v1` are both rejected — their real hosts are
   remote.
2. **`LEARNARKEN_LOCAL_ONLY=1` is a hard egress fence.** With it set, a
   non-loopback endpoint raises instead of being called. Every consumer —
   chat generation, the VLM figure path, the adversarial harness, the API
   health probe, the demo preflight — resolves its endpoint through this one
   function, so the fence has no sibling door to walk around.

Sovereignty is therefore an *enforced, testable* deployment property rather
than a promise: point the endpoint at a loopback model server, set the fence,
and a non-loopback call cannot happen.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Hosts treated as "this machine". Exact matches only — a suffix test would
#: accept `localhost.evil.example`, and a numeric-form allowance (`2130706433`)
#: would accept an obfuscated address, so both fail closed.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: Set to "1" to forbid any non-loopback generation endpoint (data-egress fence).
LOCAL_ONLY_ENV = "LEARNARKEN_LOCAL_ONLY"

_REQUIRED = (
    "MINIMAX_API_URL",
    "MINIMAX_MODEL_NAME",
    "MINIMAX_API_KEY",
    "MINIMAX_API_PROXY_TOKEN",
)
_LINE = re.compile(r"^(MINIMAX_[A-Z0-9_]+)\s*=\s*(.*)$")


class ConfigError(RuntimeError):
    """Config missing or unsafe. Callers must not proceed (INV-4)."""


def local_only_enabled() -> bool:
    """True when the data-egress fence is armed (`LEARNARKEN_LOCAL_ONLY=1`)."""
    return os.environ.get(LOCAL_ONLY_ENV, "").strip() == "1"


def _check_endpoint(url: str) -> None:
    """Validate the generation endpoint against the policy in the module docstring.

    Raises `ConfigError` on anything that would put repository content on a
    wire it should not be on. Never returns a "degraded but usable" verdict.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("https", "http") or not host:
        raise ConfigError(
            f"MINIMAX_API_URL {url!r} is not an http(s) URL with a host (fail closed)"
        )
    is_loopback = host in LOOPBACK_HOSTS
    if parts.scheme != "https" and not is_loopback:
        raise ConfigError(
            f"MINIMAX_API_URL must be https for the non-loopback host {host!r} — "
            "plaintext is accepted only for a local model server on "
            f"{sorted(LOOPBACK_HOSTS)} (fail closed)"
        )
    if local_only_enabled() and not is_loopback:
        raise ConfigError(
            f"{LOCAL_ONLY_ENV}=1 forbids the non-loopback endpoint {host!r}: "
            "evidence snippets and figure bytes would leave this machine. "
            "Point MINIMAX_API_URL at a loopback OpenAI-compatible server "
            "(llama-server / vLLM / Ollama) or unset the fence (fail closed)"
        )


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
    _check_endpoint(config["MINIMAX_API_URL"])
    return config
