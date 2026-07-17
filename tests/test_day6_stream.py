"""Day 6 hermetic tests for the streaming layer: the answer-field extractor
(think-skip, escape decoding across delta boundaries) and the OpenAI-style
SSE chunk parser + streaming client. No network."""

import json
import urllib.error

import pytest

from learnarken.answer.stream import AnswerFieldExtractor
from learnarken.llm.minimax import (
    LLMContractError,
    LLMError,
    _iter_stream_deltas,
    chat_json_stream,
)

M3_CONTENT = (
    '<think>the key "answer": "trap" inside think must not trigger</think>\n'
    '{"is_answerable": true, "answer": "Release the pressure.", "citations": []}'
)


def _feed_all(extractor: AnswerFieldExtractor, text: str, size: int) -> str:
    out = []
    for i in range(0, len(text), size):
        out.append(extractor.feed(text[i : i + size]))
    return "".join(out)


class TestAnswerFieldExtractor:
    def test_whole_content_at_once(self):
        ex = AnswerFieldExtractor()
        assert ex.feed(M3_CONTENT) == "Release the pressure."
        assert ex.done

    @pytest.mark.parametrize("size", [1, 2, 3, 7, 64])
    def test_any_delta_boundary(self, size):
        ex = AnswerFieldExtractor()
        assert _feed_all(ex, M3_CONTENT, size) == "Release the pressure."
        assert ex.done

    def test_no_think_block(self):
        ex = AnswerFieldExtractor()
        content = '{"is_answerable": true, "answer": "ok then", "citations": []}'
        assert _feed_all(ex, content, 1) == "ok then"

    def test_markdown_fence_tolerated(self):
        ex = AnswerFieldExtractor()
        content = '<think>x</think>```json\n{"is_answerable": true, "answer": "fenced"}\n```'
        assert _feed_all(ex, content, 5) == "fenced"

    @pytest.mark.parametrize("size", [1, 2, 3, 5, 11])
    def test_escapes_split_across_deltas(self, size):
        raw = 'line1\\nline2 \\"q\\" caf\\u00e9 \\ud83d\\ude00 back\\\\slash'
        content = f'<think>t</think>{{"is_answerable": false, "answer": "{raw}", "c": []}}'
        ex = AnswerFieldExtractor()
        assert _feed_all(ex, content, size) == 'line1\nline2 "q" café 😀 back\\slash'

    def test_lone_surrogate_never_emitted(self):
        content = '{"answer": "bad \\ud83d end"}'
        ex = AnswerFieldExtractor()
        out = _feed_all(ex, content, 4)
        assert out == "bad � end"
        out.encode("utf-8")  # must stay UTF-8-encodable for the SSE wire

    def test_text_after_close_quote_ignored(self):
        ex = AnswerFieldExtractor()
        out = ex.feed('{"answer": "done", "citations": [{"supporting_quote": "leak"}]}')
        assert out == "done" and ex.done
        assert ex.feed(' more "answer": "again"') == ""

    def test_missing_answer_key_emits_nothing(self):
        ex = AnswerFieldExtractor()
        assert _feed_all(ex, '<think>t</think>{"foo": 1, "bar": "baz"}', 3) == ""
        assert not ex.done


def _sse_lines(*chunks: dict, done: bool = False) -> list[bytes]:
    lines = []
    for chunk in chunks:
        lines.append(f"data: {json.dumps(chunk)}".encode())
        lines.append(b"")
    if done:
        lines.append(b"data: [DONE]")
    return lines


def _chunk(content: str, finish: str | None = None) -> dict:
    choice: dict = {"index": 0, "delta": {"content": content, "role": "assistant"}}
    if finish:
        choice["finish_reason"] = finish
    return {"choices": [choice], "model": "MiniMax-M3", "usage": None}


class TestIterStreamDeltas:
    def test_yields_deltas_in_order(self):
        lines = _sse_lines(_chunk("<think>a"), _chunk("</think>b"), _chunk("", finish="stop"))
        deltas = [d for d, _ in _iter_stream_deltas(lines)]
        assert deltas == ["<think>a", "</think>b", ""]

    def test_done_sentinel_stops(self):
        lines = _sse_lines(_chunk("x"), done=True) + [b"data: never-parsed"]
        assert [d for d, _ in _iter_stream_deltas(lines)] == ["x"]

    def test_base_resp_error_raises(self):
        lines = _sse_lines({"base_resp": {"status_code": 1004, "status_msg": "auth"}})
        with pytest.raises(LLMError, match="1004"):
            list(_iter_stream_deltas(lines))

    def test_unparseable_chunk_is_contract_error(self):
        with pytest.raises(LLMContractError, match="unparseable"):
            list(_iter_stream_deltas([b"data: {not json"]))


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return iter(self._lines)

    def __exit__(self, *exc):
        return False


class _Boom:
    """Iterates one good line, then breaks the connection mid-stream."""

    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        def gen():
            yield self._lines[0]
            raise urllib.error.URLError("reset")

        return gen()

    def __exit__(self, *exc):
        return False


@pytest.fixture
def minimax_env(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "MINIMAX_API_URL=https://x\nMINIMAX_MODEL_NAME=m\n"
        "MINIMAX_API_KEY=k\nMINIMAX_API_PROXY_TOKEN=t\n"
    )
    import learnarken.config as config
    import learnarken.llm.minimax as minimax

    monkeypatch.setattr(minimax, "load_minimax_config", lambda: config.load_minimax_config(env))
    return minimax


class TestChatJsonStream:
    def test_streams_then_parses_contract(self, monkeypatch, minimax_env):
        lines = _sse_lines(
            _chunk("<think>t</think>"),
            _chunk('{"is_answerable": true, '),
            _chunk('"answer": "yes", "citations": []}', finish="stop"),
        )
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _FakeResponse(lines))
        seen: list[str] = []
        result = chat_json_stream("sys", "user", on_delta=seen.append)
        assert "".join(seen).endswith('"citations": []}')
        assert result.parsed == {"is_answerable": True, "answer": "yes", "citations": []}
        assert result.request_payload["stream"] is True

    def test_mid_stream_failure_never_retries(self, monkeypatch, minimax_env):
        calls = []
        lines = _sse_lines(_chunk("partial"))

        def fake_urlopen(request, timeout):
            calls.append(1)
            return _Boom(lines)

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(LLMError, match="mid-stream"):
            chat_json_stream("sys", "user", on_delta=lambda t: None)
        assert len(calls) == 1  # a delta was already forwarded: no silent re-ask

    def test_empty_stream_is_contract_error(self, monkeypatch, minimax_env):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda request, timeout: _FakeResponse(_sse_lines(_chunk("", finish="stop"))),
        )
        with pytest.raises(LLMContractError, match="no content"):
            chat_json_stream("sys", "user", on_delta=lambda t: None)
