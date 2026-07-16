"""Reproduce the Day 4a embedding length-bias finding (docs/notes/day4-embedding-length-bias.md).

SELF-CONTAINED MiniMax client: the production client was removed from the
architecture by the Day 4 adjudication (docs/reviews/day4.md Part 2), but this
evidence script must stay runnable (INV-5). Credentials are read from the
FollowTheBig project's .env (the original config source, never committed).

    uv run --with requests python tools/probe_length_bias.py
"""

from __future__ import annotations

import os
from pathlib import Path

import requests

from learnarken.chunking import chunk_package

_ENV_FILE = Path.home() / "Documents/project/FollowTheBig/.env"


def _load_creds() -> dict[str, str]:
    creds = {}
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            creds[k.strip()] = v.strip().strip('"').strip("'")
    return creds


def embed(texts: list[str], mode: str) -> list[list[float]]:
    """Minimal MiniMax-native embedding call (shape measured 2026-07-15)."""
    c = _load_creds()
    r = requests.post(
        c["MINIMAX_API_URL"].rstrip("/") + "/embeddings",
        headers={
            "Authorization": f"Bearer {c['MINIMAX_API_KEY']}",
            "X-Proxy-Token": c.get("MINIMAX_API_PROXY_TOKEN", ""),
            "Content-Type": "application/json",
        },
        json={"model": "embo-01", "texts": texts, "type": mode},
        timeout=int(os.getenv("PROBE_TIMEOUT", "30")),
    )
    r.raise_for_status()
    body = r.json()
    assert body.get("base_resp", {}).get("status_code", 1) == 0, body.get("base_resp")
    return body["vectors"]


QUERY = "How do I remove the pump?"
BASE = "Remove the four mounting bolts and remove the pump."
FULL = (
    "Remove the four mounting bolts and remove the pump from the accessory gearbox pad. "
    "For part numbers, refer to ."
)
IRRELEVANT = "All open ports are capped and the work area is clean of fluid."

PROBES = [
    ("how do I take the pump off the gearbox", "four mounting bolts"),
    ("what stops the gear from retracting on the ground", "ground safety pins"),
    ("where do I put the drain container", "drain container below"),
    ("can hydraulic fluid injure me", "penetrate skin"),
]


def cosine(a: list[float], b: list[float]) -> float:
    # Vectors arrive L2-normalized (measured) — the dot product is the cosine.
    return sum(x * y for x, y in zip(a, b, strict=True))


def section_length_bias() -> None:
    print("=== Length, not meaning, drives the collapse (query held constant) ===")
    variants = [
        (BASE, "original"),
        (f"{BASE} {BASE}", "SAME sentence twice — meaning identical, length doubled"),
        (f"{BASE} {BASE} {BASE}", "same sentence three times"),
        (f"{BASE} The sky is blue. Water is wet.", "original + neutral filler"),
        (
            "Remove the four mounting bolts and remove the pump from the accessory gearbox pad.",
            "original + five RELEVANT qualifiers",
        ),
    ]
    for text, label in variants:
        vectors = embed([QUERY, text], "db")
        print(f"  {cosine(vectors[0], vectors[1]):.4f}  ({len(text.split()):2d}w)  {label}")


def section_inversion() -> None:
    print("\n=== The inversion: irrelevant-but-short beats correct-but-long ===")
    vectors = embed([QUERY, FULL, IRRELEVANT], "db")
    correct, irrelevant = cosine(vectors[0], vectors[1]), cosine(vectors[0], vectors[2])
    print(f"  {correct:.4f}  CORRECT answer  : {FULL[:56]}...")
    print(f"  {irrelevant:.4f}  IRRELEVANT chunk: {IRRELEVANT}")
    verdict = "INVERTED — length bias confirmed" if irrelevant > correct else "correct chunk wins"
    print(f"  -> {verdict}")


def section_type_matrix() -> None:
    print("\n=== type=db / type=query does not rescue it (mean rank, lower is better) ===")
    chunks = chunk_package("samples/package-a", "structure")
    cache = {mode: embed([c.text for c in chunks], mode) for mode in ("db", "query")}

    def rank_of(query_vector: list[float], doc_vectors: list[list[float]], needle: str) -> int:
        target = next(i for i, c in enumerate(chunks) if needle in c.text)
        order = sorted(range(len(doc_vectors)), key=lambda i: -cosine(query_vector, doc_vectors[i]))
        return order.index(target) + 1

    for index_mode in ("db", "query"):
        for search_mode in ("db", "query"):
            ranks = [
                rank_of(embed([q], search_mode)[0], cache[index_mode], needle)
                for q, needle in PROBES
            ]
            note = (
                "  <- vendor-documented pairing"
                if (index_mode, search_mode) == ("db", "query")
                else ""
            )
            print(
                f"  index={index_mode:5s} search={search_mode:5s}  "
                f"ranks={ranks}  mean={sum(ranks) / len(ranks):5.2f}{note}"
            )
    print(f"  ({len(chunks)} chunks in the index)")


if __name__ == "__main__":
    section_length_bias()
    section_inversion()
    section_type_matrix()
