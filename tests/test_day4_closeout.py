"""Day 4 closeout tests — red-team findings #5/#9/#10/#14 (docs/reviews/day4.md,
ruling of 2026-07-16: fix ALL remaining findings before merge).

Hermetic: Vespa's HTTP layer is monkeypatched. The live-service path is
tests/test_day4_integration.py (finding #12).
"""

import json
from pathlib import Path

import pytest
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

import learnarken.retrieval as retrieval
from learnarken.chunking.base import Chunk
from learnarken.models import Applicability, ApplicAssertion
from learnarken.vespa import store


def _chunk(cid: str, text: str = "Remove the pump.", **overrides) -> Chunk:
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


def _hit_fields(chunk: Chunk, package: str) -> dict:
    fields = store._document_fields(chunk, package)
    fields.pop("embedding", None)
    return fields


class TestYqlParameterization:
    """Red-team day4 #9: every YQL-interpolated value is validated/clamped."""

    def test_unknown_strategy_rejected_before_any_request(self, monkeypatch):
        monkeypatch.setattr(store, "_request", lambda *a, **k: pytest.fail("request sent"))
        with pytest.raises(ValueError, match="unknown strategy"):
            store.search([0.0], strategy='x" or true or "')

    def test_unsafe_package_name_rejected_before_any_request(self, monkeypatch):
        monkeypatch.setattr(store, "_request", lambda *a, **k: pytest.fail("request sent"))
        with pytest.raises(ValueError, match="invalid package name"):
            store.search([0.0], package='pkg" or true')

    def test_top_k_clamped_into_bounds(self, monkeypatch):
        captured: dict = {}

        def fake_request(url, payload=None, method="GET", timeout=30):
            captured.update(payload or {})
            return {"root": {"children": []}}

        monkeypatch.setattr(store, "_request", fake_request)
        store.search([0.0], top_k=10**9)
        assert captured["hits"] == store.MAX_TOP_K
        assert f"targetHits:{store.MAX_TOP_K}," in captured["yql"]
        store.search([0.0], top_k=0)
        assert captured["hits"] == 1


class TestPackageScope:
    """Red-team day4 #5: engine-side package filter, fail closed on leaks."""

    def test_package_filter_lands_in_yql(self, monkeypatch):
        captured: dict = {}

        def fake_request(url, payload=None, method="GET", timeout=30):
            captured.update(payload or {})
            return {"root": {"children": []}}

        monkeypatch.setattr(store, "_request", fake_request)
        store.search([0.0], package="package-a")
        assert 'package contains "package-a"' in captured["yql"]

    def test_out_of_scope_hit_fails_closed(self, monkeypatch):
        leak = {"fields": _hit_fields(_chunk("c9"), package="package-c"), "relevance": 0.9}
        monkeypatch.setattr(store, "_request", lambda *a, **k: {"root": {"children": [leak]}})
        with pytest.raises(store.VespaError, match="outside requested scope"):
            store.search([0.0], package="package-a")

    def test_in_scope_hit_returned(self, monkeypatch):
        hit = {"fields": _hit_fields(_chunk("c1"), package="package-a"), "relevance": 0.9}
        monkeypatch.setattr(store, "_request", lambda *a, **k: {"root": {"children": [hit]}})
        (result,) = store.search([0.0], package="package-a")
        assert result[0].chunk_id == "c1"

    def test_feed_requires_matching_package_names(self):
        with pytest.raises(store.VespaError, match="refusing to feed"):
            store.feed([_chunk("c1")], [[0.0]], [])
        with pytest.raises(store.VespaError, match="invalid package name"):
            store.feed([_chunk("c1")], [[0.0]], ['pkg" or true'])


class TestPinnedRevisions:
    """Red-team day4 #10 (second half): HF snapshots pinned, INV-5."""

    def test_every_provider_is_pinned_and_wired(self):
        from learnarken.embedding.providers import _LOCAL_CONFIG, DIMENSIONS, REVISIONS

        assert set(REVISIONS) == set(DIMENSIONS)
        for provider, sha in REVISIONS.items():
            assert len(sha) == 40, f"{provider} revision must be a full commit SHA"
            assert _LOCAL_CONFIG[provider]["model_kwargs"]["revision"] == sha

    def test_reranker_is_pinned(self):
        from learnarken.retrieval.hybrid import RERANKER_REVISION

        assert len(RERANKER_REVISION) == 40

    def test_verify_corpus_rejects_foreign_revision(self, tmp_path, monkeypatch):
        from learnarken.embedding.providers import DEFAULT_PROVIDER, DIMENSIONS

        chunk = _chunk("c1")
        monkeypatch.chdir(tmp_path)
        (tmp_path / retrieval.MANIFEST_PATH.name).write_text(
            json.dumps(
                {
                    "packages": ["samples/package-a"],
                    "strategy": "structure",
                    "provider": DEFAULT_PROVIDER,
                    "revision": "0" * 40,  # not the pinned snapshot
                    "dimension": DIMENSIONS[DEFAULT_PROVIDER],
                    "chunk_ids": [chunk.chunk_id],
                }
            ),
            encoding="utf-8",
        )
        import learnarken.vespa as vespa

        monkeypatch.setattr(vespa, "list_doc_ids", lambda: {chunk.chunk_id})
        with pytest.raises(ValueError, match="revision"):
            retrieval.verify_corpus([chunk], "structure")


class _FixedRetriever(BaseRetriever):
    documents: list[Document]

    def _get_relevant_documents(self, query, *, run_manager):
        return self.documents


class TestApplicabilityOverfetch:
    """Red-team day4 #14: with an 排除场合 context, Vespa modes must fetch the
    full corpus before filtering, so an inapplicable chunk at rank ≤ k cannot
    evict the applicable answer at k+1."""

    @staticmethod
    def _variant_chunk(cid: str, variant: str) -> Chunk:
        return _chunk(
            cid,
            applicability=Applicability(
                display_text=f"Variant {variant} only",
                assertions=[
                    ApplicAssertion(property_ident="variant", property_type="", values=variant)
                ],
            ),
        )

    @staticmethod
    def _applic(variant: str) -> Applicability:
        return Applicability(
            display_text=f"Variant {variant} only",
            assertions=[
                ApplicAssertion(property_ident="variant", property_type="", values=variant)
            ],
        )

    def test_applicable_answer_survives_post_filter_cut(self, monkeypatch):
        from learnarken.chunking.documents import to_document

        seen: dict = {}

        def fake_mode_retriever(mode, chunks, k, strategy, package=None):
            # Local corpus chunks (the C1/C2 guard rejects foreign ids), with
            # applicability overridden: rank 1 excluded for variant B, rank 2
            # is the real answer.
            inapplicable = chunks[0].model_copy(update={"applicability": self._applic("A")})
            applicable = chunks[1].model_copy(update={"applicability": self._applic("B")})
            seen.update(k=k, package=package, n_chunks=len(chunks), want=applicable.chunk_id)
            return _FixedRetriever(documents=[to_document(inapplicable), to_document(applicable)])

        monkeypatch.setattr(retrieval, "_mode_retriever", fake_mode_retriever)
        results = retrieval.search_package(
            "samples/package-a", "q", mode="dense", k=1, context={"variant": "B"}
        )
        assert [r.chunk.chunk_id for r in results] == [seen["want"]]
        assert seen["k"] == max(1, seen["n_chunks"])  # full-corpus overfetch bound
        assert seen["package"] == "package-a"  # engine-side scope (red-team #5)

    def test_overfetch_beyond_engine_cap_fails_closed(self, monkeypatch):
        import learnarken.vespa.store as store_mod

        monkeypatch.setattr(store_mod, "MAX_TOP_K", 5)  # corpus is 20+ chunks
        with pytest.raises(ValueError, match="incomplete filter"):
            retrieval.search_package(
                "samples/package-a", "q", mode="dense", k=1, context={"variant": "B"}
            )

    def test_no_context_keeps_requested_k(self, monkeypatch):
        seen: dict = {}

        def fake_mode_retriever(mode, chunks, k, strategy, package=None):
            seen.update(k=k)
            return _FixedRetriever(documents=[])

        monkeypatch.setattr(retrieval, "_mode_retriever", fake_mode_retriever)
        retrieval.search_package("samples/package-a", "q", mode="dense", k=3)
        assert seen["k"] == 3


class TestCloseoutSecondPass:
    """Red-team day4 C1–C7/C11 (second-pass rulings, 2026-07-16)."""

    def test_foreign_chunk_in_results_fails_closed(self, monkeypatch):
        # C1/C2: a stale or basename-colliding index must not be citable.
        from learnarken.chunking.documents import to_document

        def fake_mode_retriever(mode, chunks, k, strategy, package=None):
            return _FixedRetriever(documents=[to_document(_chunk("not-in-this-package"))])

        monkeypatch.setattr(retrieval, "_mode_retriever", fake_mode_retriever)
        with pytest.raises(ValueError, match="not in this package's corpus"):
            retrieval.search_package("samples/package-a", "q", mode="dense", k=3)

    def test_index_rejects_colliding_basenames(self):
        # C1: the basename is the engine-side scope identity.
        with pytest.raises(ValueError, match="basenames collide"):
            retrieval.index_package(["tenant-a/manual", "tenant-b/manual"])

    def test_approximate_must_be_a_real_bool(self, monkeypatch):
        # C5: a crafted string must never reach the YQL annotation.
        monkeypatch.setattr(store, "_request", lambda *a, **k: pytest.fail("request sent"))
        with pytest.raises(ValueError, match="approximate must be a bool"):
            store.search([0.0], approximate="true}or true{")

    def test_ablation_rejects_duplicate_golden_texts(self, tmp_path):
        # C6: the single-pass cache is keyed by query text.
        golden = tmp_path / "golden.jsonl"
        row = {"query_id": "q1", "query": "same text", "relevant": []}
        golden.write_text(
            json.dumps(row) + "\n" + json.dumps({**row, "query_id": "q2"}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="duplicate golden query texts"):
            retrieval.run_ablation(["samples/package-a"], golden, modes=("bm25",))

    def test_readme_tables_match_artifacts(self):
        # C4: `--check` is the drift guard — a red-team #1 style hand edit
        # (or a stale README after re-running the eval) fails the suite.
        import subprocess
        import sys as _sys

        repo = Path(__file__).parent.parent
        result = subprocess.run(  # noqa: S603
            [_sys.executable, "tools/gen_benchmark_tables.py", "--check"],
            capture_output=True,
            text=True,
            cwd=repo,
        )
        assert result.returncode == 0, result.stdout + result.stderr
