"""Day 3 retrieval tests: tokenizer, BM25 search, metrics, CLI."""

import json
from pathlib import Path

from learnarken.chunking.base import Chunk
from learnarken.cli import main
from learnarken.retrieval import search_package
from learnarken.retrieval.bm25 import BM25Index, tokenize
from learnarken.retrieval.evaluate import GoldenQuery, evaluate_strategy

SAMPLES = Path(__file__).parent.parent / "samples"
PUMP_REMOVE = "DMC-LA100-A-29-10-00-00A-520A-A"
IPD = "DMC-LA100-A-29-10-00-00A-941A-D"


class TestTokenizer:
    def test_identifiers_survive_as_single_tokens(self):
        assert "dmc-la100-a-29-10-00-00a-520a-a" in tokenize("see DMC-LA100-A-29-10-00-00A-520A-A")
        assert "la-29-4711-1" in tokenize("part LA-29-4711-1 fits")
        assert "icn-la100-29-001-01" in tokenize("figure ICN-LA100-29-001-01")

    def test_plain_words_lowercased_and_split(self):
        assert tokenize("Remove the Pump") == ["remove", "the", "pump"]

    def test_identifier_not_shredded_on_hyphen(self):
        toks = tokenize("P-1002 and 1002")
        assert "p-1002" in toks
        assert toks.count("1002") == 1  # the bare 1002, not a fragment of P-1002


def _chunk(text, dmc=PUMP_REMOVE, cid="x", icn=None):
    return Chunk(
        chunk_id=cid,
        strategy="structure",
        dmc=dmc,
        dm_title="t",
        issue_info="001-00",
        chunk_type="step",
        source_path=f"/p/{cid}",
        text=text,
        icn_refs=icn or [],
    )


class TestBm25Search:
    def test_identifier_query_hits_exact_dm_only(self):
        results = search_package(SAMPLES / "package-a", "LA-29-4711-1", k=5)
        assert results
        assert results[0].chunk.dmc == IPD
        # the bare part number must not drag in unrelated DMs
        assert all(r.chunk.dmc == IPD for r in results)

    def test_empty_corpus_returns_no_hits(self):
        assert BM25Index([]).search("anything") == []

    def test_zero_overlap_query_is_not_a_hit(self):
        idx = BM25Index([_chunk("remove the hydraulic pump")])
        assert idx.search("cabin pressurization schedule") == []


class TestMetrics:
    def test_hand_worked_case(self):
        # one relevant chunk (c2) sitting at rank 3 in the ranked list
        chunks = [_chunk("alpha", cid="c1"), _chunk("beta", cid="c2"), _chunk("gamma", cid="c3")]
        anchor = (PUMP_REMOVE, "/a")
        anchor_texts = {anchor: "beta"}
        golden = [GoldenQuery("Q1", "q", [anchor])]

        def fake_search(query, k=10):
            order = [chunks[0], chunks[2], chunks[1]]  # c2 (relevant) last -> rank 3
            from learnarken.retrieval.bm25 import ScoredChunk

            return [ScoredChunk(i + 1, 1.0, c) for i, c in enumerate(order[:k])]

        m = evaluate_strategy(chunks, fake_search, golden, anchor_texts, ks=(1, 5))
        assert m["recall@1"] == 0.0  # relevant not in top-1
        assert m["recall@5"] == 1.0  # relevant within top-5
        assert m["mrr"] == round(1 / 3, 4)  # first relevant at rank 3
        assert m["n_evaluated"] == 1

    def test_query_without_resolvable_relevant_is_skipped(self):
        chunks = [_chunk("alpha", cid="c1")]
        golden = [GoldenQuery("Q1", "q", [(PUMP_REMOVE, "/missing")])]

        def fake_search(query, k=10):
            return []

        m = evaluate_strategy(chunks, fake_search, golden, {}, ks=(5,))
        assert m["n_evaluated"] == 0


class TestRetrievalCli:
    def test_chunk_json_exit_0(self, capsys):
        assert main(["chunk", str(SAMPLES / "package-a"), "--dm", PUMP_REMOVE, "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert {c["chunk_type"] for c in payload} == {"warning", "step"}

    def test_search_human_exit_0(self, capsys):
        assert main(["search", str(SAMPLES / "package-a"), "remove hydraulic pump", "-k", "3"]) == 0
        assert "hits" in capsys.readouterr().out

    def test_search_applies_to_excludes_variant(self, capsys):
        rc = main(
            ["search", str(SAMPLES / "package-c"), "steering damper", "--applies-to", "variant=A"]
        )
        assert rc == 0
        assert "0 hits" in capsys.readouterr().out

    def test_not_a_package_exit_2(self, tmp_path):
        assert main(["chunk", str(tmp_path)]) == 2

    def test_eval_retrieval_json(self, capsys):
        rc = main(
            [
                "eval",
                "retrieval",
                "--package",
                str(SAMPLES / "package-a"),
                "--package",
                str(SAMPLES / "package-c"),
                "--golden",
                "eval/golden/day3.candidates.jsonl",
                "--json",
            ]
        )
        assert rc == 0
        report = json.loads(capsys.readouterr().out)
        # structure-aware should not lose to the recursive control on Recall@10
        results = report["results"]
        assert results["structure"]["recall@10"] >= results["recursive"]["recall@10"]

    def test_eval_missing_golden_exit_1(self):
        assert main(["eval", "retrieval", "--golden", "nope.jsonl"]) == 1
