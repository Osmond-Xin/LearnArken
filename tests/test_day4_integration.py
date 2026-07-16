"""Live Vespa integration suite (red-team day4 #12, ruling: fix all).

Skip-marked on `vespa.is_up()`: `make test` stays green on machines without
the container, but where Vespa runs (the Q6 "local green" bar) the deploy /
feed / scope-filter / delete path is exercised automatically instead of
manually. Model-loading smoke tests additionally require
`LEARNARKEN_HEAVY_TESTS=1` (they load the pinned 8B embedder / reranker).

Synthetic `itest-` documents are cleaned up in `finally`, so the suite never
disturbs the real indexed corpus — and if cleanup ever failed, the corpus
manifest verification would fail closed rather than silently comparing a
polluted index.
"""

import os
import random

import pytest

from learnarken import vespa
from learnarken.chunking.base import Chunk
from learnarken.embedding.providers import DEFAULT_PROVIDER, DIMENSIONS

pytestmark = pytest.mark.skipif(
    not vespa.is_up(), reason="Vespa container not running (see docs/local-services.md)"
)

HEAVY = os.environ.get("LEARNARKEN_HEAVY_TESTS") == "1"


def _unit_vector(seed: int) -> list[float]:
    rng = random.Random(seed)
    raw = [rng.gauss(0, 1) for _ in range(DIMENSIONS[DEFAULT_PROVIDER])]
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw]


def _chunk(cid: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=cid,
        strategy="structure",
        dmc="DMC-LA100-A-29-10-00-00A-520A-A",
        dm_title="Integration fixture",
        issue_info="001-00",
        chunk_type="step",
        source_path=f"/dmodule/itest/{cid}",
        text=text,
    )


class TestFeedSearchDeleteRoundTrip:
    def test_scope_filter_and_idempotent_delete(self):
        ids = ("itest-a", "itest-b")
        try:
            vespa.feed(
                [_chunk("itest-a", "alpha step"), _chunk("itest-b", "beta step")],
                [_unit_vector(1), _unit_vector(2)],
                ["itest-pkg-a", "itest-pkg-b"],
            )
            engine_ids = vespa.list_doc_ids()
            assert set(ids) <= engine_ids
            # Engine-side package scope (red-team #5): only the a-package doc.
            hits = vespa.search(_unit_vector(1), top_k=5, package="itest-pkg-a")
            assert [c.chunk_id for c, _ in hits] == ["itest-a"]
            # Round-trip fidelity through the summary fields.
            assert hits[0][0].text == "alpha step"
        finally:
            for cid in ids:
                vespa.delete(cid)
        assert not set(ids) & vespa.list_doc_ids()

    def test_search_validates_before_hitting_engine(self):
        with pytest.raises(ValueError, match="unknown strategy"):
            vespa.search(_unit_vector(3), strategy="not-a-strategy")


@pytest.mark.skipif(not HEAVY, reason="set LEARNARKEN_HEAVY_TESTS=1 to load local models")
class TestModelSmoke:
    """Loads the pinned snapshots (red-team #10) — a bad `revision=` pin or an
    incompatible kwarg fails here, not in the middle of an ablation run."""

    def test_query_embedding_has_schema_dimension(self):
        from learnarken.embedding.providers import embed_query_cached

        vector = embed_query_cached("hydraulic pump removal")
        assert len(vector) == DIMENSIONS[DEFAULT_PROVIDER]

    def test_reranker_loads_and_prefers_the_relevant_document(self):
        from langchain_core.documents import Document

        from learnarken.retrieval.hybrid import _reranker

        reranker = _reranker(top_n=1)
        out = reranker.compress_documents(
            [
                Document(page_content="The battery supplies current."),
                Document(page_content="Remove the hydraulic pump."),
            ],
            query="hydraulic pump removal",
        )
        assert out[0].page_content == "Remove the hydraulic pump."

    def test_dense_search_end_to_end_over_indexed_corpus(self):
        if not vespa.count():
            pytest.skip("no corpus indexed — run `learnarken index` first")
        from learnarken.retrieval import search_package

        results = search_package("samples/package-a", "hydraulic pump", mode="dense", k=3)
        assert results, "dense search over the indexed corpus returned nothing"
