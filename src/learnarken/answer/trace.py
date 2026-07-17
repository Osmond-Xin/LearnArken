"""Answer trace: one JSON file per query, five spans (Day 5, DR report §3).

The trace is the audit record that lets a wrong answer be attributed to
"the manual is wrong" vs "retrieval missed it" vs "the model hallucinated".
Location `eval/traces/` is git-ignored (per-query artifacts, reproducible
from the corpus); the format carries a version so Day 9's evidence chain can
parse it.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

TRACE_DIR = Path("eval/traces")
TRACE_FORMAT = "learnarken-answer-trace/1"


def new_trace_id() -> str:
    return time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]


def write_trace(trace_id: str, spans: dict) -> Path:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{trace_id}.json"
    path.write_text(
        json.dumps(
            {"format": TRACE_FORMAT, "trace_id": trace_id, **spans},
            indent=1,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    return path
