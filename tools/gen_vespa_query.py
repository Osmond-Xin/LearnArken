"""Write a ready-to-send Vespa search payload for docs/http/03-dense-search.http.

`nearestNeighbor` needs a 4096-float query vector, which nobody types into a
.http file. This embeds the query with the default provider (the same call the
dense retriever makes) and dumps the exact JSON body Vespa expects.

    uv run python tools/gen_vespa_query.py "engine oil servicing" --package package-a

Output defaults to var/http/dense-search.json (git-ignored), which the
REST Client file reads with `< ../../var/http/dense-search.json`.

**Local developer tool, not a runtime component.** It writes a file; it never
talks to Vespa, and nothing in `src/` imports it. Its whole purpose is to let a
human poke the loopback dev container by hand from a .http file while reading
the raw engine response.

Even so it applies the **same argument guards as the production query path**
(`vespa.store.dense_search`, red-team day4 #5 / C5): `--strategy` must be a
known chunking strategy, `--package` must match the safe-name pattern, and
`--top-k` is clamped — because these values are interpolated into the YQL
string, and a debug payload that bypasses the production constraints is a
debug payload that no longer reproduces production behaviour. Raised as F-15 in
docs/reviews/readme-refactor-2026-07-25.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from learnarken.chunking import STRATEGIES
from learnarken.embedding.providers import embed_query_cached
from learnarken.vespa.store import _SAFE_PACKAGE, MAX_TOP_K

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "var" / "http" / "dense-search.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="natural-language query to embed")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--package", default=None, help="scope to one package")
    parser.add_argument("--strategy", default=None, help="e.g. structure / recursive / semantic")
    parser.add_argument(
        "--approximate", action="store_true", help="HNSW instead of exact brute force"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    # Same guards as vespa.store.dense_search — see the module docstring.
    if args.strategy is not None and args.strategy not in STRATEGIES:
        parser.error(f"unknown strategy {args.strategy!r}; choose from {sorted(STRATEGIES)}")
    if args.package is not None and not _SAFE_PACKAGE.match(args.package):
        parser.error(f"invalid package name {args.package!r}")
    top_k = max(1, min(int(args.top_k), MAX_TOP_K))

    nn = f"{{targetHits:{top_k}, approximate:{str(args.approximate).lower()}}}"
    conditions = [f"({nn}nearestNeighbor(embedding, q))"]
    if args.strategy:
        conditions.append(f'strategy contains "{args.strategy}"')
    if args.package:
        conditions.append(f'package contains "{args.package}"')

    payload = {
        "yql": f"select * from chunk where {' and '.join(conditions)}",
        "ranking.profile": "dense",
        "input.query(q)": {"values": embed_query_cached(args.query)},
        "hits": top_k,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2))
    print(f"{args.out} written — query={args.query!r}, yql={payload['yql']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
