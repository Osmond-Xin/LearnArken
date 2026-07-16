"""Run Gemini's official Deep Research agent via the Interactions API.

Daily-cycle step 1a (研), learning workflow v2 — see docs/execution-plan.md.
Requires a paid-tier GEMINI_API_KEY (https://aistudio.google.com/apikey);
free-tier keys have no Interactions-API access. Not yet run against the live
endpoint (no key on this machine as of 2026-07-15) — verify on first use.

Usage:
    uv run --with google-genai tools/deep_research.py <prompt-file> <out-file> [--max]

--max selects deep-research-max-preview-04-2026 (slower, most comprehensive).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from google import genai

POLL_SECONDS = 15


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--max"]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set (paid tier required).", file=sys.stderr)
        return 2
    prompt = Path(args[0]).read_text(encoding="utf-8")
    out_path = Path(args[1])
    agent = (
        "deep-research-max-preview-04-2026"
        if "--max" in sys.argv
        else "deep-research-preview-04-2026"
    )

    client = genai.Client()
    interaction = client.interactions.create(input=prompt, agent=agent, background=True)
    print(f"interaction {interaction.id} started with {agent}; polling every {POLL_SECONDS}s")

    while True:
        interaction = client.interactions.get(interaction.id)
        if interaction.status == "completed":
            out_path.write_text(interaction.outputs[-1].text, encoding="utf-8")
            print(f"report written to {out_path}")
            return 0
        if interaction.status == "failed":
            print(f"research failed: {interaction.error}", file=sys.stderr)
            return 1
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
