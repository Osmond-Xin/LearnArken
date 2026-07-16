"""BM25 retrieval with an identifier-preserving tokenizer (Day 3 → Day 4a).

Tutorial 02 §1 / failure mode 1: a standard analyzer shreds identifiers like
`DMC-LA100-A-29-10-00-00A-520A-A` or `P/N 1234-567` on punctuation, so an
identifier query then drags in every doc sharing a bare numeric fragment. The
single highest-leverage IR fix in a technical corpus is to keep identifiers as
whole tokens. `tokenize` does exactly that.

Day 4a (D13): the engine underneath is LangChain's `BM25Retriever` (which
wraps the same rank-bm25 library), with `tokenize` plugged in as its
`preprocess_func`. Three Day 3 behaviors are ours, layered on top, because the
framework has no hook for them:

1. identifiers living in XML *attributes* (own DMC, ICN refs, dmRefs) are
   appended to the indexed text so identifier lookups resolve;
2. a hit requires actual token overlap — BM25 gives negative-IDF terms nonzero
   scores, so score sign is not a hit test (red-team #1);
3. ranked results carry scores (`ScoredChunk`), which the retriever interface
   drops.

`BM25Index.retriever` exposes the LangChain object for framework composition
(EnsembleRetriever fusion etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_community.retrievers import BM25Retriever

from learnarken.chunking.base import Chunk
from learnarken.chunking.documents import to_document

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


def _indexed_text(chunk: Chunk) -> str:
    """Chunk text plus its attribute-borne identifiers (behavior 1)."""
    return " ".join([chunk.text, chunk.dmc, *chunk.icn_refs, *chunk.outbound_dm_refs])


@dataclass
class ScoredChunk:
    rank: int
    score: float
    chunk: Chunk


class BM25Index:
    """In-process BM25 over chunks: LangChain BM25Retriever + our domain layer."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        corpus = [tokenize(_indexed_text(c)) for c in chunks]
        self._token_sets = [set(tokens) for tokens in corpus]
        # rank-bm25 (and thus the LC retriever) cannot build over an empty
        # corpus; guard so search returns [].
        if chunks:
            retriever = BM25Retriever.from_documents(
                [
                    to_document(c).model_copy(update={"page_content": _indexed_text(c)})
                    for c in chunks
                ],
                preprocess_func=tokenize,
            )
            # The augmented text exists only to build the scoring index (the
            # vectorizer is frozen at construction). The *returned* documents
            # must carry the clean chunk text — otherwise fusion/rerank layers
            # downstream would rerank and display identifier-stuffed text, and
            # from_document() would reconstruct a Chunk whose text differs from
            # the source (self-review finding, 2026-07-16).
            retriever.docs = [to_document(c) for c in chunks]
            self.retriever: BM25Retriever | None = retriever
        else:
            self.retriever = None

    def search(self, query: str, k: int = 10) -> list[ScoredChunk]:
        if self.retriever is None or k <= 0:
            return []
        query_tokens = tokenize(query)
        query_token_set = set(query_tokens)
        # The retriever interface drops scores; its `vectorizer` is the live
        # rank-bm25 index built from the same corpus order (behavior 3).
        scores = self.retriever.vectorizer.get_scores(query_tokens)
        ranked = sorted(enumerate(scores), key=lambda kv: kv[1], reverse=True)
        out: list[ScoredChunk] = []
        for idx, score in ranked:
            # Behavior 2 (red-team #1): require real token overlap; score sign
            # is not a reliable hit test under negative IDF.
            if not (query_token_set & self._token_sets[idx]):
                continue
            out.append(
                ScoredChunk(rank=len(out) + 1, score=round(float(score), 4), chunk=self.chunks[idx])
            )
            if len(out) >= k:
                break
        return out
