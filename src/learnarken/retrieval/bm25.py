"""BM25 retrieval with an identifier-preserving tokenizer (Day 3).

Tutorial 02 §1 / failure mode 1: a standard analyzer shreds identifiers like
`DMC-LA100-A-29-10-00-00A-520A-A` or `P/N 1234-567` on punctuation, so an
identifier query then drags in every doc sharing a bare numeric fragment. The
single highest-leverage IR fix in a technical corpus is to keep identifiers as
whole tokens. `tokenize` does exactly that, and BM25Index is a thin wrapper
over rank-bm25 (decision Q1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from learnarken.chunking.base import Chunk

# An identifier: an alphanumeric run containing a digit and a '-', '/' or '_'
# internal separator (DMCs, ICNs, part numbers). Matched first, kept whole and
# lowercased. `P/N 1234-567` and a bare `1234-567` both surface `1234-567`.
_IDENTIFIER = re.compile(r"[A-Za-z0-9]+(?:[-/_][A-Za-z0-9]+)+")
_WORD = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, but emit identifiers as single unsplit tokens."""
    tokens: list[str] = []
    pos = 0
    for m in _IDENTIFIER.finditer(text):
        if any(c.isdigit() for c in m.group()):
            tokens.extend(w.lower() for w in _WORD.findall(text[pos : m.start()]))
            tokens.append(m.group().lower())
            pos = m.end()
    tokens.extend(w.lower() for w in _WORD.findall(text[pos:]))
    return tokens


@dataclass
class ScoredChunk:
    rank: int
    score: float
    chunk: Chunk


class BM25Index:
    """In-process BM25 index over a chunk list (no persistence — corpus is tiny)."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        # Index the chunk text plus its identifiers (own DMC, ICN refs, outbound
        # dmRefs) so identifier lookups resolve — these live in XML attributes,
        # not element text, so they are absent from `text` (tutorial 02 §1).
        corpus = [
            tokenize(" ".join([c.text, c.dmc, *c.icn_refs, *c.outbound_dm_refs])) for c in chunks
        ]
        self._token_sets = [set(toks) for toks in corpus]
        # rank-bm25 cannot build over an empty corpus; guard so search returns [].
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, k: int = 10) -> list[ScoredChunk]:
        if self._bm25 is None or k <= 0:
            return []
        query_tokens = set(tokenize(query))
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(enumerate(scores), key=lambda kv: kv[1], reverse=True)
        out: list[ScoredChunk] = []
        for idx, score in ranked:
            # A hit needs actual token overlap. BM25 assigns negative scores to
            # matches on terms present in most docs (negative IDF), so the score
            # sign is NOT a reliable hit test (red-team #1) — check overlap.
            if not (query_tokens & self._token_sets[idx]):
                continue
            out.append(
                ScoredChunk(rank=len(out) + 1, score=round(float(score), 4), chunk=self.chunks[idx])
            )
            if len(out) >= k:
                break
        return out
