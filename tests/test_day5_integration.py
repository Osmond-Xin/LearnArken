"""Day 5 live golden-set suite (spec decision 5): real Vespa + Neo4j + models
+ MiniMax-M3. Gated on LEARNARKEN_HEAVY_TESTS=1 (paid LLM calls) plus the
services being up; the hermetic gate tests live in tests/test_day5_answer.py.

Answerable golden questions must produce a non-refused answer whose citations
intersect the query's golden-relevant chunk set (chunk-ID verification);
no-answer golden traps must produce the refusal placeholder.
"""

import os

import pytest

from learnarken import graph, vespa
from learnarken.answer import PLACEHOLDER, answer_question
from learnarken.answer.engine import DEFAULT_PACKAGES
from learnarken.config import ConfigError, load_minimax_config

HEAVY = os.environ.get("LEARNARKEN_HEAVY_TESTS") == "1"


def _config_present() -> bool:
    try:
        load_minimax_config()
        return True
    except ConfigError:
        return False


pytestmark = pytest.mark.skipif(
    not (HEAVY and vespa.is_up() and graph.is_up() and _config_present()),
    reason="needs LEARNARKEN_HEAVY_TESTS=1, Vespa+Neo4j up, and MiniMax config",
)

# Golden query ids: three answerable across categories + two no-answer traps.
ANSWERABLE_IDS = ("Q001", "C101", "Q011")  # procedural / paraphrase / warning
NO_ANSWER_IDS = ("Q020", "C113")


def _golden_by_id():
    from learnarken.chunking import chunk_package
    from learnarken.retrieval import _dedupe_chunks
    from learnarken.retrieval.evaluate import _anchor_chunk_sets, load_golden, resolve_anchors

    golden = load_golden("eval/golden/day4.jsonl")
    chunks = _dedupe_chunks(
        [c for pkg in DEFAULT_PACKAGES for c in chunk_package(pkg, "structure")]
    )
    anchors = {a for q in golden for a in q.relevant}
    resolved = resolve_anchors(list(DEFAULT_PACKAGES), anchors)
    by_id = {}
    for q in golden:
        relevant_ids = (
            set().union(*_anchor_chunk_sets(q, chunks, resolved)) if q.relevant else set()
        )
        by_id[q.query_id] = (q, relevant_ids)
    return by_id


@pytest.fixture(scope="module")
def golden_by_id():
    return _golden_by_id()


class TestGoldenAnswerable:
    @pytest.mark.parametrize("query_id", ANSWERABLE_IDS)
    def test_cited_answer_hits_golden_chunks(self, golden_by_id, query_id):
        query, relevant_ids = golden_by_id[query_id]
        assert relevant_ids, f"{query_id} resolved to no chunks — fixture problem"
        result = answer_question(query.query)
        assert not result.refused, f"{query_id} refused (gate={result.refusal_gate})"
        cited_ids = {c.chunk_id for c in result.citations}
        # Chunk-ID verification (decision 5): the cited evidence must
        # intersect the human-annotated relevant set for this question.
        assert cited_ids & relevant_ids, f"{query_id}: cited {cited_ids} ∉ golden {relevant_ids}"
        for citation in result.citations:  # decision 3: traceable to source
            assert citation.dmc.startswith("DMC-") and citation.source_path


class TestGoldenNoAnswer:
    @pytest.mark.parametrize("query_id", NO_ANSWER_IDS)
    def test_trap_gets_placeholder(self, golden_by_id, query_id):
        query, relevant_ids = golden_by_id[query_id]
        assert not relevant_ids, f"{query_id} is not a no-answer trap — fixture problem"
        result = answer_question(query.query)
        assert result.refused, f"{query_id} was answered instead of refused"
        assert result.answer_text == PLACEHOLDER
        assert result.refusal_gate in ("threshold", "llm", "citation-validation")
