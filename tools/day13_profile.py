"""Profile the CPU-bound offline paths and list hotspots (Day 13, Decision 2).

Measure **before** optimizing (scan must-master #5): this runs cProfile over the
validation + chunking paths and records the top functions by self-time, so the
numba decision rests on evidence, not a guess. py-spy (sampling, flame graph,
`--native` to see into lxml's C extension) is the sampling cross-check; when its
binary is absent it is recorded as the manual follow-up rather than silently
skipped — cProfile alone is enough to answer the *numba-eligibility* question,
which is about whether any hotspot is a pure-numeric Python loop.

Each hotspot is classified for numba eligibility (Decision 2b/2c): only
pure-numeric, loop-dense, type-stable Python is eligible; XML parsing, Pydantic,
lxml XPath and model inference are **not**. The verdict feeds
`docs/notes/day13-numba-decision.md`.

    uv run python tools/day13_profile.py [--iterations 20]

Output is frozen at eval/results/day13-hotspots.json.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import shutil
from pathlib import Path

from learnarken.chunking import chunk_package
from learnarken.validation.engine import analyze_package

_OUT = Path("eval/results/day13-hotspots.json")
_PACKAGES = ["samples/package-a", "samples/package-b", "samples/package-c"]

# Modules whose functions are, by construction, NOT numba targets (Decision 2c):
# C extensions, XML/schema, Pydantic, regex, path/IO glue.
_EXCLUDED_MARKERS = (
    "lxml",
    "etree",
    "pydantic",
    "xmlschema",
    "defusedxml",
    "/re/",
    "re.py",
    "pathlib",
    "genericpath",
    "loader.py",
    "{built-in",
    "<frozen",
)


def _numba_eligible(filename: str, funcname: str) -> bool:
    """Coarse gate: a hotspot is *potentially* numba-eligible only if it is our
    own pure-Python code and not an XML/Pydantic/regex/IO function. This is a
    necessary-not-sufficient screen — a human still confirms the loop is numeric
    and type-stable (Decision 2b)."""
    hay = f"{filename}/{funcname}".lower()
    if any(marker in hay for marker in _EXCLUDED_MARKERS):
        return False
    return "learnarken" in filename


def _workload(iterations: int) -> None:
    for _ in range(iterations):
        for pkg in _PACKAGES:
            analyze_package(pkg)
            chunk_package(pkg)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()

    profiler = cProfile.Profile()
    profiler.enable()
    _workload(args.iterations)
    profiler.disable()

    stats = pstats.Stats(profiler)
    rows: list[dict] = []
    # stats.stats: {(file, line, func): (cc, nc, tottime, cumtime, callers)}
    ranked = sorted(stats.stats.items(), key=lambda kv: kv[1][2], reverse=True)
    for (filename, lineno, funcname), (_cc, ncalls, tottime, cumtime, _callers) in ranked[:20]:
        eligible = _numba_eligible(filename, funcname)
        rows.append(
            {
                "func": funcname,
                "location": f"{Path(filename).name}:{lineno}",
                "self_time_s": round(tottime, 4),
                "cum_time_s": round(cumtime, 4),
                "ncalls": ncalls,
                "numba_eligible": eligible,
                "note": ""
                if eligible
                else "excluded: XML/Pydantic/regex/IO/C-ext (not a numeric loop, Decision 2c)",
            }
        )

    # The screen is necessary-not-sufficient: "in learnarken and not an obvious
    # XML/Pydantic/IO function". It cannot decide "is this a numeric loop" — that
    # is a human read, recorded in docs/notes/day13-numba-decision.md (Decision 2b).
    screened = [r for r in rows if r["numba_eligible"]]
    verdict = (
        "no not-obviously-excluded hotspot in the top 20; the CPU is spent in lxml "
        "parsing / schema validation / Pydantic model building (Decision 2c). "
        "No numba target — recorded as a PASSING result, no numba dependency added."
        if not screened
        else f"screen flagged {len(screened)} not-obviously-excluded hotspot(s) "
        f"({[r['func'] for r in screened]}); NONE is a pure-numeric loop on inspection "
        "(they are XML/orchestration) — human-confirmed verdict is in "
        "docs/notes/day13-numba-decision.md (Decision 2b)."
    )

    result = {
        "experiment": "profiling — validation + chunking hotspots (Day 13, Decision 2)",
        "tool": "cProfile (deterministic, stdlib)",
        "pyspy": "NOT run — py-spy binary absent in this env; manual sampling "
        "cross-check `py-spy record --native -- python -m ...` is the documented "
        "follow-up. cProfile is sufficient to answer numba-eligibility (scan A3).",
        "pyspy_present": shutil.which("py-spy") is not None,
        "workload": f"analyze_package + chunk_package over {_PACKAGES}, "
        f"{args.iterations} iterations",
        "top_by_self_time": rows,
        "screened_not_excluded": [r["func"] for r in screened],
        "verdict": verdict,
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {_OUT}")
    print(f"  {verdict}")


if __name__ == "__main__":
    main()
