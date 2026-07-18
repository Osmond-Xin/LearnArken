"""`make demo` preflight: every dependency checked fail-closed, with the fix
command printed instead of a stack trace (SPEC day6, `make demo` section)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnarken import graph, vespa  # noqa: E402
from learnarken.answer.engine import THRESHOLD_ARTIFACT, load_threshold  # noqa: E402
from learnarken.config import REPO_ROOT, ConfigError, load_minimax_config  # noqa: E402

CHECKS = []


def check(label: str, fix: str):
    def wrap(fn):
        CHECKS.append((label, fix, fn))
        return fn

    return wrap


@check("repo root cwd", f"cd {REPO_ROOT} && make demo (trace/manifest paths are cwd-relative)")
def _cwd() -> bool:
    return Path.cwd().resolve() == REPO_ROOT


@check(".env with MINIMAX_* config", "cp .env.example .env, then fill the MINIMAX_* values")
def _env() -> bool:
    try:
        load_minimax_config()
        return True
    except ConfigError as exc:
        print(f"    ({exc})")
        return False


@check(
    f"refusal-threshold artifact ({THRESHOLD_ARTIFACT.name})",
    "uv run python tools/measure_refusal_threshold.py",
)
def _threshold() -> bool:
    try:
        load_threshold()
        return True
    except ValueError:
        return False


@check("Vespa (127.0.0.1:8080)", "docker start learnarken-vespa  (see docs/local-services.md)")
def _vespa() -> bool:
    return vespa.is_up()


@check("Neo4j (127.0.0.1:7474)", "docker start learnarken-neo4j  (see docs/local-services.md)")
def _neo4j() -> bool:
    return graph.is_up()


def main() -> int:
    failed = 0
    for label, fix, fn in CHECKS:
        ok = fn()
        print(f"  {'✅' if ok else '❌'} {label}")
        if not ok:
            print(f"     fix: {fix}")
            failed += 1
    if failed:
        print(f"\npreflight failed ({failed} check(s)) — demo not started (fail closed)")
        return 1
    print("preflight OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
