"""Graph expansion as the third RRF route (Day 11, spec §2).

Candidate *expansion*, not score reweighting: this retriever exists to rescue
chunks that are not in the semantic/lexical candidate pool at all (tutorial 14
§2). Flow: deterministic entity linking (`entity_link`) → 1-2 hop `:REFS`
neighborhood (`graph.neighborhood`, both directions) → the seed and neighbor
DMs' chunks as a ranked list for `EnsembleRetriever`.

The "virtual ranking" (spec T1): hop 0 (linked DMs' own chunks) first, then
hop 1, hop 2 in the store's deterministic order (out-edges before in-edges,
then dmc); within a DM, chunks sort by source_path. Zero randomness — the
same query yields a byte-identical list (INV-5).

Degradation: no linked entities ⇒ empty result (a query that names no corpus
entity gets no graph signal — fail closed, INV-4). Neo4j unreachable ⇒ empty
result with a logged warning; `run_ablation` refuses up front instead
(`graph.is_up()`), so an eval row can never silently degrade to plain hybrid.
"""

from __future__ import annotations

import logging

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from learnarken.chunking.base import Chunk
from learnarken.chunking.documents import to_document
from learnarken.retrieval.entity_link import EntityLexicon, build_lexicon, link_entities

logger = logging.getLogger("learnarken")


class GraphExpansionRetriever(BaseRetriever):
    chunks_by_dmc: dict[str, list[Chunk]]  # values sorted by source_path
    lexicon: EntityLexicon
    k: int = 20
    depth: int = 2

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        from learnarken import graph

        entities = link_entities(query, self.lexicon)
        if not entities:
            return []
        seeds = sorted({dmc for e in entities for dmc in e.dmcs})
        try:
            neighbors, truncated = graph.neighborhood(seeds, depth=self.depth)
        except graph.GraphError as exc:
            logger.warning("graph route degraded to nothing (Neo4j unreachable): %s", exc)
            return []
        if truncated:
            logger.warning("graph expansion truncated at the node cap (seeds=%s)", seeds)

        ordered: list[tuple[str, int, str]] = [(dmc, 0, "seed") for dmc in seeds]
        ordered.extend((n.dmc, n.hops, n.direction) for n in neighbors)
        documents: list[Document] = []
        for dmc, hops, direction in ordered:
            for chunk in self.chunks_by_dmc.get(dmc, ()):  # non-corpus node: no chunks
                document = to_document(chunk)
                document.metadata["graph_hop"] = hops
                document.metadata["graph_direction"] = direction
                documents.append(document)
                if len(documents) >= self.k:
                    return documents
        return documents


def graph_expansion_retriever(chunks: list[Chunk], k: int = 20) -> GraphExpansionRetriever:
    """Build the route from the same chunk list the other routes hold (T7)."""
    by_dmc: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        by_dmc.setdefault(chunk.dmc, []).append(chunk)
    for group in by_dmc.values():
        group.sort(key=lambda c: c.source_path)
    return GraphExpansionRetriever(chunks_by_dmc=by_dmc, lexicon=build_lexicon(chunks), k=k)
