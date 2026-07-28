#!/usr/bin/env python3
"""Reduce a full answer trace to the evidence a published claim needs.

    tools/public_trace.py eval/traces/<id>.json docs/assets/demo-answer.trace.json

A README GIF is the only artifact in this repository with no reproduction path,
so each one ships with the trace of the run inside it. The *full* trace is not
what should be published, though: it carries `llm.request_payload` (the entire
prompt, system rules and evidence included) and `generation.raw_content` (the
model's raw output, think block and all). `answer/trace.py` already refuses to
write traces at all in public-demo mode for that reason — publishing them here
by hand would contradict it.

What survives is what a reader needs to check the claims made beside the GIF:

* `llm_called` — whether the model ran at all. A `threshold` refusal never calls
  it, which is the claim the refusal GIF makes.
* `generation.answer_text_emitted` — whether the model produced any answer text.
  Empty means the retraction had nothing visible to withdraw, which is the claim
  the retraction GIF makes.
* `outcome` — the gate, the citations, the routed action, verbatim.
* `authorisation`, `sources_excluded`, `rerank` — what was withheld and why, and
  the scores behind the threshold decision.

Dropped, deliberately: the prompt, the raw model output, and the retrieved chunk
bodies. The corpus is synthetic (INV-1) so nothing here is confidential — the
point is that the shape of what gets published should not depend on that.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DROPPED = (
    "llm.request_payload — the full prompt, including system rules and evidence",
    "generation.raw_content — the model's raw output, think block included",
    "retrieval, graph — retrieved chunk bodies; the corpus is public under samples/",
)


def reduce_trace(full: dict) -> dict:
    llm = full.get("llm") or {}
    generation = full.get("generation") or {}
    parsed = generation.get("parsed") or {}
    answer = parsed.get("answer")
    return {
        "format": full.get("format"),
        "trace_id": full.get("trace_id"),
        "note": (
            "Reduced from the full trace for publication; see tools/public_trace.py. "
            "Dropped: " + "; ".join(DROPPED)
        ),
        "question": full.get("question"),
        "packages": full.get("packages"),
        "mode": full.get("mode"),
        "authorisation": full.get("authorisation"),
        "rerank": full.get("rerank"),
        "sources_excluded": full.get("sources_excluded"),
        # The claim "refused before the model was ever called" is exactly this
        # key being false — the engine writes no `llm` span when it refuses at
        # the retrieval threshold.
        "llm_called": bool(llm),
        "llm": {"model": llm.get("model"), "usage": llm.get("usage")} if llm else None,
        "generation": {
            "is_answerable": parsed.get("is_answerable"),
            # The claim "nothing visible was withdrawn" is this being empty: the
            # client streams the answer field, so no answer text means no text
            # ever reached the screen to retract.
            "answer_text_emitted": bool(answer and answer.strip()),
            "answer_chars": len(answer) if isinstance(answer, str) else None,
        }
        if generation
        else None,
        "outcome": full.get("outcome"),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    source, target = Path(argv[1]), Path(argv[2])
    reduced = reduce_trace(json.loads(source.read_text(encoding="utf-8")))
    target.write_text(json.dumps(reduced, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{source} -> {target} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
