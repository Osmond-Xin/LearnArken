#!/usr/bin/env python3
"""Check the README's demo GIF claims against the traces committed beside them.

    uv run python tools/verify_demo_traces.py

A GIF is the one artifact in this repository with no reproduction path, so each
one ships with the trace of the run inside it (red-team F-19). This turns the
two load-bearing sentences in README §1 into something a reader — or CI — can
settle without watching a picture:

* "refused before the model was ever called" ⇒ `llm_called` is false. The engine
  writes no `llm` span at all when it refuses at the retrieval threshold.
* "nothing visible was withdrawn" ⇒ `answer_text_emitted` is false. The client
  streams the answer field, so an empty one means no text ever reached the
  screen to retract.

Exits non-zero on any mismatch. What it cannot check is that the trace id in
each file is the one visible in its GIF — that stays a human read of the frame,
and it is the whole reason the id is on screen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"

#: name -> (llm_called, answer_text_emitted, gate, has_citations)
EXPECTED = {
    "answer": (True, True, None, True),
    "refusal": (False, None, "threshold", False),
    "retraction": (True, False, "llm", False),
}


def check() -> list[str]:
    """Return a list of mismatches; empty means the claims hold."""
    problems: list[str] = []
    for name, (llm_called, emitted, gate, cited) in EXPECTED.items():
        path = ASSETS / f"demo-{name}.trace.json"
        gif = ASSETS / f"demo-{name}.gif"
        if not path.exists():
            problems.append(f"{name}: {path.name} is missing")
            continue
        if not gif.exists():
            problems.append(f"{name}: {gif.name} is missing — the trace has no picture to back")
            continue
        trace = json.loads(path.read_text(encoding="utf-8"))
        outcome = trace.get("outcome") or {}
        generation = trace.get("generation") or {}
        actual = (
            trace.get("llm_called"),
            generation.get("answer_text_emitted"),
            outcome.get("gate"),
            bool(outcome.get("citations")),
        )
        if actual != (llm_called, emitted, gate, cited):
            problems.append(f"{name}: expected {(llm_called, emitted, gate, cited)}, got {actual}")
        # A published trace must stay reduced: the prompt and the model's raw
        # output are dropped on purpose (see tools/public_trace.py).
        for leaked in ("request_payload", "raw_content", "retrieval", "graph"):
            if leaked in json.dumps(trace.get("llm") or {}) + json.dumps(generation):
                problems.append(f"{name}: {leaked} leaked into a published trace")
    return problems


def main() -> int:
    for name in EXPECTED:
        path = ASSETS / f"demo-{name}.trace.json"
        if not path.exists():
            continue
        trace = json.loads(path.read_text(encoding="utf-8"))
        outcome = trace.get("outcome") or {}
        generation = trace.get("generation") or {}
        print(
            f"{name:11} llm_called={trace.get('llm_called')!s:<5} "
            f"answer_text_emitted={generation.get('answer_text_emitted')!s:<5} "
            f"gate={outcome.get('gate')!s:<10} trace={trace.get('trace_id')}"
        )
    problems = check()
    if problems:
        print("\nMISMATCH:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print("\nAll README demo claims hold against the committed traces.")
    print("Still a human read: that each trace id above is the one visible in its GIF.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
