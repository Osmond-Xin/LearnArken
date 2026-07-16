"""Dense retrieval as a LangChain retriever over the Vespa store (Day 4a).

The LangChain face of `vespa/store.py`: embeds the query with the default
provider (bake-off winner) and runs exact `nearestNeighbor`. Exposing it as a
`BaseRetriever` is what lets `EnsembleRetriever` fuse it with BM25 (D13:
framework primitives for the pipeline, our modules underneath).

Fail-closed (INV-4): if Vespa is unreachable or the embedding call fails, the
exception propagates. There is no silent fallback to BM25 — a dense/hybrid
answer that is secretly lexical would misreport what was measured.
"""

from __future__ import annotations

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from learnarken import vespa
from learnarken.chunking.documents import to_document
from learnarken.embedding.providers import get_embeddings


class VespaDenseRetriever(BaseRetriever):
    """nearestNeighbor over the chunks previously fed by `learnarken index`."""

    k: int = 10
    strategy: str = "structure"  # only match chunks fed under this strategy
    package: str | None = None  # engine-side scope filter (red-team day4 #5)
    approximate: bool = False  # exact by default: no ANN confound at toy scale
    embeddings: Embeddings | None = Field(default=None, exclude=True)

    def _embedder(self) -> Embeddings:
        return self.embeddings or get_embeddings()

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        if self.embeddings is None:
            from learnarken.embedding.providers import embed_query_cached

            vector = embed_query_cached(query)
        else:
            vector = self._embedder().embed_query(query)
        hits = vespa.search(
            vector,
            top_k=self.k,
            strategy=self.strategy,
            package=self.package,
            approximate=self.approximate,
        )
        documents = []
        for chunk, score in hits:
            document = to_document(chunk)
            document.metadata["dense_score"] = score
            documents.append(document)
        return documents
