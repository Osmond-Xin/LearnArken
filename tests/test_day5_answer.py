"""Day 5 hermetic tests: config hardening, M3 content parsing, the three
fail-closed answer gates, and CLI exit codes. No network, no services, no
models — the live golden-set suite is tests/test_day5_integration.py."""

import json

import pytest
from langchain_core.documents import Document

import learnarken.answer.engine as engine
from learnarken.answer import PLACEHOLDER, answer_question
from learnarken.chunking.base import Chunk
from learnarken.config import ConfigError, load_minimax_config
from learnarken.graph import GraphFacts
from learnarken.llm.minimax import _strip_think


def _chunk(cid: str, text: str = "Remove the pump.") -> Chunk:
    return Chunk(
        chunk_id=cid,
        strategy="structure",
        dmc="DMC-LA100-A-29-10-00-00A-520A-A",
        dm_title="Hydraulic pump",
        issue_info="001-00",
        chunk_type="step",
        source_path=f"/dmodule/content/procedure/mainProcedure/proceduralStep[{cid}]",
        text=text,
    )


class TestConfigHardening:
    """Red-team day4 #7 hardening, applied from the start (spec Interfaces)."""

    def test_missing_env_fails_closed(self, tmp_path):
        with pytest.raises(ConfigError, match="fail closed"):
            load_minimax_config(tmp_path / ".env")

    def test_missing_key_fails_closed(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("MINIMAX_API_URL=https://x\nMINIMAX_MODEL_NAME=m\n")
        with pytest.raises(ConfigError, match="missing MiniMax config key"):
            load_minimax_config(env)

    def test_plain_http_rejected(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(
            "MINIMAX_API_URL=http://attacker\nMINIMAX_MODEL_NAME=m\n"
            "MINIMAX_API_KEY=k\nMINIMAX_API_PROXY_TOKEN=t\n"
        )
        with pytest.raises(ConfigError, match="https"):
            load_minimax_config(env)

    def test_non_minimax_keys_ignored(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(
            "OPENAI_API_KEY=leak\nMINIMAX_API_URL=https://x\nMINIMAX_MODEL_NAME=m\n"
            "MINIMAX_API_KEY=k\nMINIMAX_API_PROXY_TOKEN=t\n"
        )
        config = load_minimax_config(env)
        assert "OPENAI_API_KEY" not in config


class TestThinkStripping:
    """Both shapes observed live (spec Probe findings): <think> prefix always;
    a ```json fence appears on longer prompts even with response_format set."""

    def test_plain_json_passthrough(self):
        assert json.loads(_strip_think('{"a": 1}')) == {"a": 1}

    def test_think_prefix_stripped(self):
        content = '<think>reasoning\nmore</think>\n{"a": 1}'
        assert json.loads(_strip_think(content)) == {"a": 1}

    def test_think_plus_fence_stripped(self):
        content = '<think>r</think>\n```json\n{"a": 1}\n```'
        assert json.loads(_strip_think(content)) == {"a": 1}

    def test_fence_without_think(self):
        assert json.loads(_strip_think('```json\n{"a": 1}\n```')) == {"a": 1}


class _FakeChat:
    """Stands in for llm.chat_json; records whether it was called."""

    def __init__(self, parsed: dict):
        self.parsed = parsed
        self.called = False

    def __call__(self, system: str, user: str, **kwargs):
        from learnarken.llm.minimax import ChatResult

        self.called = True
        self.system, self.user = system, user
        return ChatResult(
            parsed=self.parsed,
            raw_content=json.dumps(self.parsed),
            model="MiniMax-M3",
            usage={"total_tokens": 1},
            request_payload={"messages": []},
        )


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Wire the engine hermetically: two evidence chunks, score 0.9, threshold 0.5."""
    monkeypatch.chdir(tmp_path)  # traces land in tmp, not the repo
    chunks = [_chunk("c1", "Release the pressure."), _chunk("c2", "Remove the bolts.")]
    monkeypatch.setattr(engine, "chunk_package", lambda pkg, strategy: list(chunks))
    monkeypatch.setattr(engine, "verify_corpus", lambda c, s: None)
    monkeypatch.setattr(engine, "load_threshold", lambda: 0.5)
    monkeypatch.setattr(
        engine,
        "_candidates",
        lambda question, c, mode: [
            Document(page_content=ch.text, metadata={"chunk_id": ch.chunk_id}) for ch in chunks
        ],
    )
    import learnarken.retrieval.hybrid as hybrid

    def fake_rerank(query, documents, k=10):
        from learnarken.chunking.documents import to_document

        return [(to_document(ch), 0.9 - i * 0.1) for i, ch in enumerate(chunks)][:k]

    monkeypatch.setattr(hybrid, "rerank_scored", fake_rerank)
    import learnarken.graph as graph_module

    monkeypatch.setattr(
        graph_module,
        "facts",
        lambda dmcs: [GraphFacts(dmc=d, title="Hydraulic pump") for d in dict.fromkeys(dmcs)],
    )
    return chunks


class TestAnswerGates:
    def _run(self, monkeypatch, parsed: dict):
        fake = _FakeChat(parsed)
        monkeypatch.setattr(engine, "chat_json", fake)
        return fake, answer_question("How do I remove the pump?")

    def test_answered_with_backfilled_citations(self, monkeypatch, wired):
        fake, result = self._run(
            monkeypatch,
            {
                "is_answerable": True,
                "answer": "Release pressure, remove bolts.",
                "citations": ["c1", "c2"],
            },
        )
        assert not result.refused
        assert [c.chunk_id for c in result.citations] == ["c1", "c2"]
        # DMC and XPath come from chunk metadata, never from the LLM (decision 3)
        assert result.citations[0].dmc.startswith("DMC-LA100")
        assert result.citations[0].source_path.startswith("/dmodule/")
        assert result.graph_facts and result.graph_facts[0].dmc.startswith("DMC-")

    def test_llm_says_unanswerable_gets_placeholder(self, monkeypatch, wired):
        fake, result = self._run(
            monkeypatch, {"is_answerable": False, "answer": "", "citations": []}
        )
        assert result.refused and result.answer_text == PLACEHOLDER
        assert result.refusal_gate == "llm"

    def test_invalid_citation_fails_closed(self, monkeypatch, wired):
        fake, result = self._run(
            monkeypatch,
            {"is_answerable": True, "answer": "Fabricated.", "citations": ["not-retrieved"]},
        )
        assert result.refused and result.refusal_gate == "citation-validation"
        assert result.answer_text == PLACEHOLDER

    def test_empty_citations_on_claimed_answer_fails_closed(self, monkeypatch, wired):
        fake, result = self._run(
            monkeypatch, {"is_answerable": True, "answer": "Trust me.", "citations": []}
        )
        assert result.refused and result.refusal_gate == "citation-validation"

    def test_contract_violation_fails_closed(self, monkeypatch, wired):
        fake, result = self._run(
            monkeypatch, {"is_answerable": "yes", "answer": 42, "citations": "c1"}
        )
        assert result.refused and result.refusal_gate == "llm-contract"

    def test_below_threshold_never_calls_llm(self, monkeypatch, wired):
        import learnarken.retrieval.hybrid as hybrid

        monkeypatch.setattr(hybrid, "rerank_scored", lambda q, d, k=10: [(d[0], 0.01)] if d else [])
        fake, result = self._run(
            monkeypatch, {"is_answerable": True, "answer": "x", "citations": ["c1"]}
        )
        assert result.refused and result.refusal_gate == "threshold"
        assert not fake.called  # short-circuit: the LLM is never reached

    def test_trace_file_written_with_spans(self, monkeypatch, wired, tmp_path):
        fake, result = self._run(
            monkeypatch,
            {"is_answerable": True, "answer": "Answer.", "citations": ["c1"]},
        )
        trace = json.loads((tmp_path / "eval/traces" / f"{result.trace_id}.json").read_text())
        assert {"retrieval", "rerank", "llm", "generation", "graph", "outcome"} <= set(trace)
        assert trace["outcome"]["refused"] is False


class TestQueryCli:
    def test_exit_codes(self, monkeypatch, capsys):
        from learnarken.answer.models import AnswerResult
        from learnarken.cli import main

        def fake_answer(refused: bool):
            return lambda *a, **k: AnswerResult(
                question="q",
                answer_text=PLACEHOLDER if refused else "The answer.",
                refused=refused,
                refusal_gate="llm" if refused else None,
                trace_id="t-1",
            )

        import learnarken.answer as answer_module

        monkeypatch.setattr(answer_module, "answer_question", fake_answer(False))
        assert main(["query", "q?"]) == 0
        monkeypatch.setattr(answer_module, "answer_question", fake_answer(True))
        assert main(["query", "q?"]) == 3
        assert PLACEHOLDER in capsys.readouterr().out

    def test_fail_closed_exit_one(self, monkeypatch, capsys):
        import learnarken.answer as answer_module
        from learnarken.cli import main

        def boom(*a, **k):
            raise ValueError("no refusal-threshold artifact (fail closed)")

        monkeypatch.setattr(answer_module, "answer_question", boom)
        assert main(["query", "q?"]) == 1
        assert "fail closed" in capsys.readouterr().err
