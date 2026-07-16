"""Day 3 retrieval tests: tokenizer, BM25 search, metrics, CLI."""

import json
from pathlib import Path

from learnarken.chunking.base import Chunk
from learnarken.cli import main
from learnarken.retrieval import search_package
from learnarken.retrieval.bm25 import BM25Index, tokenize
from learnarken.retrieval.evaluate import GoldenQuery, ResolvedAnchor, evaluate_strategy

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

    def test_pn_prefix_and_bare_part_number_agree(self):
        assert "1234-567" in tokenize("P/N 1234-567")
        assert "1234-567" in tokenize("part 1234-567")


def _chunk(text, dmc=PUMP_REMOVE, cid="x", icn=None, source_path=None, strategy="structure"):
    return Chunk(
        chunk_id=cid,
        strategy=strategy,
        dmc=dmc,
        dm_title="t",
        issue_info="001-00",
        chunk_type="step",
        source_path=source_path or f"/p/{cid}",
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

    def test_common_term_present_in_all_docs_still_hits(self):
        # red-team #1: a term with negative IDF must not be dropped as "no overlap"
        idx = BM25Index([_chunk("remove the pump", cid="a"), _chunk("remove the filter", cid="b")])
        assert {r.chunk.chunk_id for r in idx.search("remove")} == {"a", "b"}

    def test_nonpositive_k_returns_empty(self):
        idx = BM25Index([_chunk("remove the pump")])
        assert idx.search("pump", k=0) == []


class TestMetrics:
    def test_hand_worked_case(self):
        # structure chunk c2 sits at the anchor XPath and lands at rank 3
        chunks = [
            _chunk("alpha", cid="c1", source_path="/a/1"),
            _chunk("beta", cid="c2", source_path="/anchor"),
            _chunk("gamma", cid="c3", source_path="/a/3"),
        ]
        anchor = (PUMP_REMOVE, "/anchor")
        resolved = {anchor: ResolvedAnchor("/anchor", "beta")}
        golden = [GoldenQuery("Q1", "q", [anchor])]

        def fake_search(query, k=10):
            order = [chunks[0], chunks[2], chunks[1]]  # c2 (relevant) last -> rank 3
            from learnarken.retrieval.bm25 import ScoredChunk

            return [ScoredChunk(i + 1, 1.0, c) for i, c in enumerate(order[:k])]

        m = evaluate_strategy(chunks, fake_search, golden, resolved, ks=(1, 5))
        assert m["recall@1"] == 0.0  # relevant not in top-1
        assert m["recall@5"] == 1.0  # relevant within top-5
        assert m["mrr"] == round(1 / 3, 4)  # first relevant at rank 3
        assert m["n_evaluated"] == 1

    def test_structure_relevance_is_xpath_not_substring(self):
        # short anchor text must NOT mark an unrelated same-DMC chunk relevant
        chunks = [
            _chunk("Install the new gasket", cid="c1", source_path="/step[1]"),
            _chunk("Install", cid="c2", source_path="/step[2]"),
        ]
        anchor = (PUMP_REMOVE, "/step[1]")
        golden = [GoldenQuery("Q1", "q", [anchor])]

        def fake_search(query, k=10):
            from learnarken.retrieval.bm25 import ScoredChunk

            return [ScoredChunk(1, 1.0, chunks[1])]  # returns the WRONG (c2) chunk

        resolved = {anchor: ResolvedAnchor("/step[1]", "Install the new gasket")}
        m = evaluate_strategy(chunks, fake_search, golden, resolved)
        assert m["recall@5"] == 0.0  # c2 is not relevant despite containing "Install"

    def test_partial_multi_anchor_does_not_inflate_recall(self):
        # 2 golden anchors; anchor A maps to a chunk, anchor B resolves but maps
        # to no chunk. Retrieving A must give recall 0.5, not 1.0 (red-team R5).
        chunks = [_chunk("alpha", cid="cA", source_path="/A")]
        a1, a2 = (PUMP_REMOVE, "/A"), (PUMP_REMOVE, "/B")
        resolved = {
            a1: ResolvedAnchor("/A", "alpha"),
            a2: ResolvedAnchor("/B-unmatched", "beta text"),  # no chunk at this path
        }
        golden = [GoldenQuery("Q1", "q", [a1, a2])]

        def fake_search(query, k=10):
            from learnarken.retrieval.bm25 import ScoredChunk

            return [ScoredChunk(1, 1.0, chunks[0])]  # covers a1 only

        m = evaluate_strategy(chunks, fake_search, golden, resolved, ks=(5,))
        assert m["recall@5"] == 0.5  # missing anchor stays in the denominator

    def test_no_answer_query_scored_as_refusal(self):
        chunks = [_chunk("hydraulic pump", cid="c1")]
        golden = [GoldenQuery("N1", "engine oil filter", [])]

        def empty_search(query, k=10):
            return []

        def hallucinating_search(query, k=10):
            from learnarken.retrieval.bm25 import ScoredChunk

            return [ScoredChunk(1, 0.1, chunks[0])]

        good = evaluate_strategy(chunks, empty_search, golden, {})
        bad = evaluate_strategy(chunks, hallucinating_search, golden, {})
        assert good["n_no_answer"] == 1 and good["zero_hit_rate"] == 1.0
        assert bad["zero_hit_rate"] == 0.0  # penalized for hallucinating a hit

    def test_unmapped_anchor_counts_as_zero_recall_not_skipped(self):
        # an answerable query whose anchor maps to no chunk must not shrink the
        # denominator — it counts as answerable with zero recall (fail closed)
        chunks = [_chunk("alpha", cid="c1")]
        golden = [GoldenQuery("Q1", "q", [(PUMP_REMOVE, "/missing")])]

        def fake_search(query, k=10):
            return []

        m = evaluate_strategy(chunks, fake_search, golden, {}, ks=(5,))
        assert m["n_evaluated"] == 1
        assert m["n_unmapped"] == 1
        assert m["recall@5"] == 0.0


class TestRetrievalCli:
    def test_chunk_json_exit_0(self, capsys):
        assert main(["chunk", str(SAMPLES / "package-a"), "--dm", PUMP_REMOVE, "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert {c["chunk_type"] for c in payload} == {"precondition", "warning", "step", "closeout"}

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

    def test_top_k_rejects_nonpositive(self):
        import pytest

        with pytest.raises(SystemExit):  # argparse rejects -k 0
            main(["search", str(SAMPLES / "package-a"), "pump", "-k", "0"])

    def test_eval_default_command_runs(self, capsys):
        # the no-arg default must not trip the fail-closed anchor check
        rc = main(["eval", "retrieval", "--json"])
        assert rc == 0
        report = json.loads(capsys.readouterr().out)
        assert report["results"]["structure"]["n_unmapped"] == 0

    def test_eval_ambiguous_anchor_exit_1(self, tmp_path, capsys):
        bad = tmp_path / "amb.jsonl"
        # anchor with no positional predicate matches all three steps -> ambiguous
        bad.write_text(
            '{"query_id":"Q1","query":"q","relevant":[{"dmc":"DMC-LA100-A-29-10-00-00A-520A-A",'
            '"source_path":"/dmodule/content/procedure/mainProcedure/proceduralStep"}]}\n',
            encoding="utf-8",
        )
        rc = main(
            ["eval", "retrieval", "--package", str(SAMPLES / "package-a"), "--golden", str(bad)]
        )
        assert rc == 1
        assert "do not resolve" in capsys.readouterr().err

    def test_eval_malformed_golden_exit_1(self, tmp_path, capsys):
        bad = tmp_path / "malformed.jsonl"
        bad.write_text('{"query_id":"Q1","query":"q"}\n', encoding="utf-8")  # missing 'relevant'
        assert main(["eval", "retrieval", "--golden", str(bad)]) == 1

    def test_eval_unresolved_anchor_exit_1(self, tmp_path, capsys):
        bad = tmp_path / "bad.jsonl"
        bad.write_text(
            '{"query_id":"Q1","query":"q","relevant":'
            '[{"dmc":"DMC-LA100-A-29-10-00-00A-520A-A","source_path":"/dmodule/nope"}]}\n',
            encoding="utf-8",
        )
        rc = main(
            ["eval", "retrieval", "--package", str(SAMPLES / "package-a"), "--golden", str(bad)]
        )
        assert rc == 1
        assert "do not resolve" in capsys.readouterr().err

    def test_eval_nonobject_golden_row_exit_1(self, tmp_path):
        bad = tmp_path / "scalar.jsonl"
        bad.write_text("1\n", encoding="utf-8")  # a bare scalar, not an object
        assert main(["eval", "retrieval", "--golden", str(bad)]) == 1

    def test_eval_scalar_xpath_anchor_exit_1(self, tmp_path):
        # a count()/string() XPath returns a float, not an element -> unresolved (R5)
        bad = tmp_path / "scalar_xpath.jsonl"
        bad.write_text(
            '{"query_id":"Q1","query":"q","relevant":'
            '[{"dmc":"DMC-LA100-A-29-10-00-00A-520A-A","source_path":"count(/dmodule)"}]}\n',
            encoding="utf-8",
        )
        assert (
            main(
                ["eval", "retrieval", "--package", str(SAMPLES / "package-a"), "--golden", str(bad)]
            )
            == 1
        )

    def test_eval_bad_package_diagnosed_as_not_a_package(self, tmp_path, capsys):
        # bad --package must report "not a directory", not "anchors do not resolve" (R4)
        golden = tmp_path / "na.jsonl"
        golden.write_text(
            '{"query_id":"Q1","query":"q","relevant":'
            '[{"dmc":"DMC-LA100-A-29-10-00-00A-520A-A","source_path":"/dmodule/content"}]}\n',
            encoding="utf-8",
        )
        rc = main(
            ["eval", "retrieval", "--package", str(tmp_path / "nope"), "--golden", str(golden)]
        )
        assert rc == 1
        assert "not a directory" in capsys.readouterr().err

    def test_duplicate_packages_never_exceed_recall_1(self, capsys):
        # passing the same package twice must not inflate recall above 1.0
        rc = main(
            [
                "eval",
                "retrieval",
                "--package",
                str(SAMPLES / "package-a"),
                "--package",
                str(SAMPLES / "package-a"),
                "--package",
                str(SAMPLES / "package-c"),
                "--json",
            ]
        )
        assert rc == 0
        report = json.loads(capsys.readouterr().out)
        for m in report["results"].values():
            assert m["recall@10"] <= 1.0 and m["ndcg@10"] <= 1.0

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
