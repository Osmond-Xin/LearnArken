"""Day 4a tests: providers, Document bridge, RRF fusion, mode plumbing.

Hermetic — no network, no Vespa, no model weights. The live-service
integration suite (red-team day4 #12) is tests/test_day4_integration.py;
the closeout-fix tests are tests/test_day4_closeout.py.
"""

from datetime import date

import pytest
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from learnarken.chunking.base import Chunk
from learnarken.chunking.documents import from_document, to_document
from learnarken.embedding import DIMENSION, DIMENSIONS
from learnarken.embedding.providers import DEFAULT_PROVIDER
from learnarken.retrieval import search_package
from learnarken.retrieval.bm25 import BM25Index
from learnarken.retrieval.hybrid import RRF_K, hybrid_retriever


def _chunk(cid: str, text: str, **overrides) -> Chunk:
    fields = dict(
        chunk_id=cid,
        strategy="structure",
        dmc="DMC-LA100-A-29-10-00-00A-520A-A",
        dm_title="Hydraulic pump",
        issue_info="001-00",
        chunk_type="step",
        source_path=f"/dmodule/content/procedure/mainProcedure/proceduralStep[{cid}]",
        text=text,
    )
    fields.update(overrides)
    return Chunk(**fields)


class TestDocumentBridge:
    def test_round_trip_lossless(self):
        chunk = _chunk(
            "c1",
            "Discharge the accumulator.",
            has_warning=True,
            outbound_dm_refs=["DMC-LA100-A-29-00-00-00A-040A-D"],
            icn_refs=["ICN-LA100-29-001-01"],
            effective_date=date(2026, 5, 1),
        )
        assert from_document(to_document(chunk)) == chunk

    def test_page_content_is_chunk_text(self):
        assert to_document(_chunk("c1", "some text")).page_content == "some text"


class _FixedRetriever(BaseRetriever):
    """Returns a fixed ranked Document list — for hand-worked fusion tests."""

    documents: list[Document]

    def _get_relevant_documents(self, query, *, run_manager):
        return self.documents


def _doc(cid: str) -> Document:
    return Document(page_content=f"text {cid}", metadata={"chunk_id": cid})


class TestRRFHandWorked:
    """Spec concept #2: hand-compute RRF on a tiny example, assert the code agrees."""

    def test_fused_order_matches_hand_computation(self):
        # Arm A ranks: x, y, z — Arm B ranks: y, z, x  (equal weights, c=60)
        arm_a = _FixedRetriever(documents=[_doc("x"), _doc("y"), _doc("z")])
        arm_b = _FixedRetriever(documents=[_doc("y"), _doc("z"), _doc("x")])
        from langchain_classic.retrievers import EnsembleRetriever

        fused = EnsembleRetriever(
            retrievers=[arm_a, arm_b], weights=[0.5, 0.5], c=RRF_K, id_key="chunk_id"
        ).invoke("anything")
        got = [d.metadata["chunk_id"] for d in fused]
        # Hand computation, score = Σ 0.5 * 1/(60+rank):
        #   x: 1/61 + 1/63 = 0.03227   y: 1/62 + 1/61 = 0.03252   z: 1/63 + 1/62 = 0.03200
        # → y > x > z
        assert got == ["y", "x", "z"]

    def test_same_chunk_from_both_arms_fuses_by_chunk_id(self):
        # Same chunk_id but DIFFERENT page_content (BM25 arm indexes augmented
        # text) — without id_key these would be treated as two documents.
        a = Document(page_content="clean text", metadata={"chunk_id": "same"})
        b = Document(page_content="clean text DMC-AUGMENTED", metadata={"chunk_id": "same"})
        from langchain_classic.retrievers import EnsembleRetriever

        fused = EnsembleRetriever(
            retrievers=[
                _FixedRetriever(documents=[a]),
                _FixedRetriever(documents=[b]),
            ],
            weights=[0.5, 0.5],
            c=RRF_K,
            id_key="chunk_id",
        ).invoke("anything")
        assert len(fused) == 1


class TestBM25OnLangChain:
    def test_identifier_still_whole_token_through_retriever(self):
        chunks = [
            _chunk("c1", "Remove the pump.", dmc="DMC-LA100-A-29-10-00-00A-520A-A"),
            _chunk(
                "c2",
                "Battery terminals supply current.",
                dmc="DMC-LA100-A-24-50-00-00A-520A-A",
                source_path="/dmodule/content/procedure/mainProcedure/proceduralStep[9]",
            ),
        ]
        hits = BM25Index(chunks).search("DMC-LA100-A-29-10-00-00A-520A-A", k=5)
        assert [h.chunk.chunk_id for h in hits] == ["c1"]

    def test_retriever_exposed_for_composition(self):
        index = BM25Index([_chunk("c1", "alpha beta")])
        assert index.retriever is not None
        docs = index.retriever.invoke("alpha")
        assert docs and docs[0].metadata["chunk_id"] == "c1"


class TestModePlumbing:
    def test_unknown_mode_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="unknown mode"):
            search_package("samples/package-a", "q", mode="bm42")

    def test_hybrid_retriever_refuses_empty_corpus(self):
        with pytest.raises(ValueError, match="empty chunk list"):
            hybrid_retriever([])


class TestBM25DocumentHygiene:
    def test_returned_documents_carry_clean_text_but_score_on_identifiers(self):
        # Self-review finding 2026-07-16: augmented text must feed ONLY the
        # scorer; returned documents (what fusion/rerank/from_document see)
        # must carry the source chunk text.
        chunk = _chunk("c1", "Remove the pump.", icn_refs=["ICN-LA100-29-001-01"])
        index = BM25Index([chunk])
        docs = index.retriever.invoke("ICN-LA100-29-001-01")  # attribute-borne id
        assert docs, "identifier from XML attributes must still be searchable"
        assert docs[0].page_content == "Remove the pump."  # clean, not augmented


class TestFusionRefusalGuard:
    def test_bm25_arm_refuses_unknown_identifier_inside_fusion(self):
        # red-team day4 #6: the retriever handed to EnsembleRetriever must
        # apply the token-overlap guard, or fusion votes for arbitrary docs
        # on an unknown part number.
        chunks = [
            _chunk("c1", "Remove the pump."),
            _chunk(
                "c2",
                "Battery terminals supply current.",
                source_path="/dmodule/content/procedure/mainProcedure/proceduralStep[9]",
            ),
        ]
        retriever = BM25Index(chunks).retriever
        assert retriever.invoke("LA-99-0000-0") == []  # unknown identifier -> refuse
        assert retriever.invoke("pump")  # known term still retrieves


class TestProviderRegistry:
    def test_default_dimension_is_provider_aware(self):
        # red-team day4 #11: DIMENSION must track the actual default provider.
        assert DEFAULT_PROVIDER == "qwen3-8b"
        assert DIMENSION == DIMENSIONS[DEFAULT_PROVIDER] == 4096

    def test_unknown_provider_rejected(self):
        import pytest as _pytest

        from learnarken.embedding.providers import get_embeddings

        with _pytest.raises(ValueError, match="unknown embedding provider"):
            get_embeddings("minimax")  # removed from the architecture (Part 2)
