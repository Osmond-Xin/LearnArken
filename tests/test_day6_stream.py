"""Day 6 hermetic tests for the streaming layer: the answer-field extractor
(think-skip, escape decoding across delta boundaries) and the OpenAI-style
SSE chunk parser + streaming client — plus the completion-budget contract the
non-streaming client shares with it. No network."""

import json
import urllib.error

import pytest

import learnarken.llm.minimax as minimax_module
from learnarken.answer.stream import AnswerFieldExtractor
from learnarken.llm.minimax import (
    LLMContractError,
    LLMError,
    _iter_stream_deltas,
    chat_json,
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


#: A deadline far enough away that these parser tests never trip it.
_FAR = float("inf")


class TestIterStreamDeltas:
    def test_yields_deltas_in_order(self):
        lines = _sse_lines(_chunk("<think>a"), _chunk("</think>b"), _chunk("", finish="stop"))
        deltas = [d for d, _ in _iter_stream_deltas(lines, _FAR)]
        assert deltas == ["<think>a", "</think>b", ""]

    def test_done_sentinel_stops(self):
        lines = _sse_lines(_chunk("x"), done=True) + [b"data: never-parsed"]
        assert [d for d, _ in _iter_stream_deltas(lines, _FAR)] == ["x"]

    def test_base_resp_error_raises(self):
        lines = _sse_lines({"base_resp": {"status_code": 1004, "status_msg": "auth"}})
        with pytest.raises(LLMError, match="1004"):
            list(_iter_stream_deltas(lines, _FAR))

    def test_unparseable_chunk_is_contract_error(self):
        with pytest.raises(LLMContractError, match="unparseable"):
            list(_iter_stream_deltas([b"data: {not json"], _FAR))

    def test_extra_choices_refused(self):
        """Round 8 P2: the payload never asks for n>1, so a second choice is a
        response we did not request — the non-streaming path already said so."""
        chunk = _chunk("x")
        chunk["choices"] = chunk["choices"] * 2
        with pytest.raises(LLMContractError, match="exactly one choice"):
            list(_iter_stream_deltas(_sse_lines(chunk), _FAR))

    def test_usage_only_chunk_is_tolerated(self):
        """A chunk with no `choices` at all is a keepalive/usage frame."""
        lines = _sse_lines({"usage": {"completion_tokens": 5}, "model": "m"})
        assert [d for d, _ in _iter_stream_deltas(lines, _FAR)] == [""]


class _FakeResponse:
    """Stands in for the urlopen response: iterable over raw lines, and
    closable — the deadline watchdog closes it to unblock a stuck read."""

    def __init__(self, lines):
        self._lines = lines
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._lines)

    def close(self):
        self.closed = True


class _Boom(_FakeResponse):
    """Iterates one good line, then breaks the connection mid-stream."""

    def __iter__(self):
        def gen():
            yield self._lines[0]
            raise urllib.error.URLError("reset")

        return gen()


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

    def test_budget_truncation_says_so(self, monkeypatch, minimax_env):
        """A completion cut off by max_tokens must name the budget, not surface
        as unparseable JSON: measured live 2026-07-27, M3's think block alone
        ran to 7305 completion tokens and the old 2048 budget truncated it."""
        lines = _sse_lines(
            _chunk("<think>reasoning that never ends"),
            _chunk("</think>", finish="length"),
        )
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _FakeResponse(lines))
        with pytest.raises(LLMContractError, match="truncated at the max_tokens budget"):
            chat_json_stream("sys", "user", on_delta=lambda t: None)

    def test_truncation_is_reported_before_the_parse_error(self, monkeypatch, minimax_env):
        """Truncation that also happens to leave unparseable JSON must still be
        reported as truncation — that is the actionable half."""
        lines = _sse_lines(_chunk('<think>t</think>{"is_answerable": tr', finish="length"))
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _FakeResponse(lines))
        with pytest.raises(LLMContractError, match="truncated at the max_tokens budget"):
            chat_json_stream("sys", "user", on_delta=lambda t: None)

    def test_truncation_beats_the_empty_content_error(self, monkeypatch, minimax_env):
        """A terminal chunk carrying `length` but no deltas must still report the
        budget, not the generic 'no content' message (red-team round 4 P2)."""
        lines = _sse_lines(_chunk("", finish="length"))
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _FakeResponse(lines))
        with pytest.raises(LLMContractError, match="truncated at the max_tokens budget"):
            chat_json_stream("sys", "user", on_delta=lambda t: None)

    def test_other_terminal_reasons_fail_closed(self, monkeypatch, minimax_env):
        """`content_filter` and friends are not a complete answer."""
        lines = _sse_lines(_chunk('{"is_answerable": true, "answer": "x", "c": []}'))
        lines += _sse_lines(_chunk("", finish="content_filter"))
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _FakeResponse(lines))
        with pytest.raises(LLMContractError, match="content_filter"):
            chat_json_stream("sys", "user", on_delta=lambda t: None)

    def test_missing_terminal_reason_fails_closed(self, monkeypatch, minimax_env):
        """Round 6 P1: a stream that ends without the service saying it finished
        is indistinguishable from a truncated one. Live 2026-07-27 both paths
        report 'stop', so requiring it costs no legitimate traffic."""
        lines = _sse_lines(_chunk('{"is_answerable": true, "answer": "x", "c": []}'))
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _FakeResponse(lines))
        with pytest.raises(LLMContractError, match="finish_reason=None"):
            chat_json_stream("sys", "user", on_delta=lambda t: None)

    def test_deadline_stops_an_sse_keepalive_flood(self, monkeypatch, minimax_env):
        """Round 7 P1: `: ping` comment lines keep the socket busy and yield no
        chunk, so a deadline checked per *chunk* never fires."""
        lines = [b": ping", b""] * 50
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _FakeResponse(lines))
        ticks = iter([0.0, 0.0] + [10_000.0] * 200)
        monkeypatch.setattr(minimax_module.time, "monotonic", lambda: next(ticks))
        with pytest.raises(LLMError, match="deadline mid-stream"):
            chat_json_stream("s", "u", on_delta=lambda t: None, timeout=300)

    def test_content_after_a_terminal_reason_is_refused(self, monkeypatch, minimax_env):
        """Round 7 P2: a delta arriving after the service said it finished is
        not part of a completion we can vouch for."""
        lines = _sse_lines(
            _chunk('{"is_answerable": true, "answer": "ok", "c": []}', finish="stop"),
            _chunk(" and also this"),
        )
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _FakeResponse(lines))
        with pytest.raises(LLMContractError, match="after finish_reason"):
            chat_json_stream("s", "u", on_delta=lambda t: None)

    def test_deadline_stops_a_trickling_stream(self, monkeypatch, minimax_env):
        """A socket timeout only catches an *idle* stream; one that trickles
        forever would hold a demo concurrency slot (round 6 P1)."""
        lines = _sse_lines(*[_chunk("tick") for _ in range(5)])
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _FakeResponse(lines))
        clock = iter([0.0, 0.0, 1.0, 10_000.0, 10_001.0])
        monkeypatch.setattr(minimax_module.time, "monotonic", lambda: next(clock))
        with pytest.raises(LLMError, match="deadline mid-stream"):
            chat_json_stream("sys", "user", on_delta=lambda t: None, timeout=300)

    def test_streaming_stop_is_not_treated_as_truncation(self, monkeypatch, minimax_env):
        lines = _sse_lines(
            _chunk('{"is_answerable": true, "answer": "ok", "citations": []}', finish="stop")
        )
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _FakeResponse(lines))
        assert chat_json_stream("s", "u", on_delta=lambda t: None).parsed["answer"] == "ok"

    def test_retries_share_one_wall_clock_deadline(self, monkeypatch, minimax_env):
        """Round 5 P2: `timeout` is a per-socket idle timeout, so three retries
        used to mean 3× the wall clock holding a demo concurrency slot."""
        seen: list[float] = []
        now = [0.0]  # a clock that only advances while we "wait"

        def fake_urlopen(request, timeout):
            seen.append(timeout)
            raise urllib.error.URLError("down")

        def advance(seconds: float) -> None:
            now[0] += 100

        monkeypatch.setattr(minimax_module.time, "monotonic", lambda: now[0])
        monkeypatch.setattr(minimax_module.time, "sleep", advance)
        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(LLMError):
            chat_json_stream("s", "u", on_delta=lambda t: None, timeout=300)
        assert seen == [300.0, 200.0, 100.0], "each attempt must inherit the remaining time"

    def test_deadline_never_yields_a_non_positive_timeout(self, monkeypatch, minimax_env):
        """An exhausted deadline must still make a bounded attempt, not pass 0
        (which urllib would read as 'no timeout')."""
        clock = iter([0.0, 10_000.0])
        monkeypatch.setattr(minimax_module.time, "monotonic", lambda: next(clock))
        seen: list[float] = []

        def fake_urlopen(request, timeout):
            seen.append(timeout)
            raise urllib.error.HTTPError("u", 400, "boom", {}, None)  # not retryable

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(LLMError):
            chat_json_stream("s", "u", on_delta=lambda t: None, timeout=300)
        assert seen == [1.0]

    def test_default_budget_covers_the_measured_worst_case(self):
        """The 2026-07-27 live measurement (one question, repeats at temperature
        0): 1888 / 1467 / 3464 / 7305 completion tokens. The default must clear
        the worst of those with room, or truncation returns."""
        assert minimax_module._MAX_TOKENS >= 2 * 7305


class _JSONResponse:
    """Non-streaming urlopen stand-in: one JSON body, bounded read, closable."""

    def __init__(self, body: dict):
        self._body = json.dumps(body).encode()
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, amt: int | None = None) -> bytes:
        return self._body if amt is None else self._body[:amt]

    def close(self):
        self.closed = True


def _completion(content: str, finish: str | None = None) -> dict:
    choice: dict = {"index": 0, "message": {"role": "assistant", "content": content}}
    if finish:
        choice["finish_reason"] = finish
    return {"base_resp": {"status_code": 0}, "choices": [choice], "model": "m", "usage": {}}


class TestChatJsonBudget:
    """The non-streaming client is the CLI's generation path, so it needs the
    same truncation contract as the streamed one."""

    def test_budget_truncation_says_so(self, monkeypatch, minimax_env):
        body = _completion('<think>endless</think>{"is_answerable": tr', finish="length")
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _JSONResponse(body))
        with pytest.raises(LLMContractError, match="truncated at the max_tokens budget"):
            chat_json("sys", "user")

    def test_complete_completion_parses(self, monkeypatch, minimax_env):
        body = _completion(
            '<think>t</think>{"is_answerable": true, "answer": "ok", "citations": []}',
            finish="stop",
        )
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _JSONResponse(body))
        assert chat_json("sys", "user").parsed["answer"] == "ok"


class _ErrorBody:
    """An HTTPError body that never ends unless the read is bounded."""

    def __init__(self):
        self.requested = []

    def read(self, amt=None):
        self.requested.append(amt)
        if amt is None:
            raise AssertionError("an unbounded error-body read would hang here")
        return b"x" * amt


class TestChatJsonErrors:
    def test_http_error_is_not_retried_as_unreachable(self, monkeypatch, minimax_env):
        """HTTPError subclasses URLError, so the retry clause used to swallow it
        and report a 401 as 'unreachable' after three attempts (round 6 P2)."""
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(1)
            raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(LLMError, match="HTTP 401"):
            chat_json("sys", "user")
        assert len(calls) == 1, "a 401 is not transient: no retry"

    def test_transient_http_status_is_retried(self, monkeypatch, minimax_env):
        """Reordering the clauses must not lose the retry a 502 deserves."""
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(1)
            raise urllib.error.HTTPError("u", 502, "Bad Gateway", {}, None)

        monkeypatch.setattr(minimax_module.time, "sleep", lambda s: None)
        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(LLMError, match="HTTP 502"):
            chat_json("sys", "user")
        assert len(calls) == 3

    def test_error_body_is_never_read(self, monkeypatch, minimax_env):
        """Round 9 P1: capping the bytes did not cap the wall clock — a peer
        trickling 199 bytes over minutes held the slot through the deadline. The
        body is not read at all now; the status is the actionable part."""
        body = _ErrorBody()
        exc = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        monkeypatch.setattr(exc, "read", body.read)
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda request, timeout: (_ for _ in ()).throw(exc)
        )
        with pytest.raises(LLMError, match="HTTP 401"):
            chat_json("sys", "user")
        assert body.requested == []

    def test_non_json_200_body_is_a_contract_error(self, monkeypatch, minimax_env):
        """A WAF/proxy HTML page served with status 200 (round 7 P2)."""

        class _Html:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, amt=None):
                return b"<html>blocked</html>"

            def close(self):
                pass

        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _Html())
        with pytest.raises(LLMContractError, match="not JSON"):
            chat_json("sys", "user")

    def test_error_body_never_reaches_the_message(self, monkeypatch, minimax_env):
        """Round 8 P2: the API forwards LLMError text to the demo visitor, and an
        upstream error body can echo the prompt, evidence, or auth diagnostics."""
        exc = urllib.error.HTTPError("u", 500, "boom", {}, None)
        monkeypatch.setattr(exc, "read", lambda amt=None: b"Authorization: Bearer sk-secret")
        monkeypatch.setattr(minimax_module.time, "sleep", lambda s: None)
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda request, timeout: (_ for _ in ()).throw(exc)
        )
        with pytest.raises(LLMError) as caught:
            chat_json("sys", "user")
        assert "sk-secret" not in str(caught.value)
        assert "HTTP 500" in str(caught.value)

    def test_non_object_json_body_is_a_contract_error(self, monkeypatch, minimax_env):
        """Round 8 P2: a JSON array with HTTP 200 would sail past every
        `body.get(...)` as an opaque internal error instead of a refusal."""

        class _Arr(_JSONResponse):
            def __init__(self):
                self._body = b"[]"
                self.closed = False

        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _Arr())
        with pytest.raises(LLMContractError, match="expected a JSON object body"):
            chat_json("sys", "user")

    def test_multiple_choices_refused(self, monkeypatch, minimax_env):
        body = _completion('{"a": 1}', finish="stop")
        body["choices"] = body["choices"] * 2
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _JSONResponse(body))
        with pytest.raises(LLMContractError, match="exactly one choice"):
            chat_json("sys", "user")


class TestLateThinkCloseTag:
    """M3 sometimes emits `</think>` a token late, stranding the JSON's opening
    brace inside the block. A salvage that re-spliced the object across that
    boundary was built and then removed: the reasoning text is attacker-reachable
    (an uploaded module becomes evidence), and red team rounds 5, 8 and 9 each
    broke the narrowing. Every one of these now fails closed."""

    def _refused(self, monkeypatch, content):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda request, timeout: _JSONResponse(_completion(content, finish="stop")),
        )
        with pytest.raises(LLMContractError, match="not JSON"):
            chat_json("sys", "user")

    def test_swallowed_opening_brace_is_refused(self, monkeypatch, minimax_env):
        self._refused(
            monkeypatch,
            '<think>so I write {</think>"is_answerable": true, "answer": "ok", "c": []}',
        )

    def test_swallowed_first_key_is_refused(self, monkeypatch, minimax_env):
        self._refused(
            monkeypatch, '<think>x {"is_answerable</think>": true, "answer": "ok", "c": []}'
        )

    def test_complete_object_inside_think_is_refused(self, monkeypatch, minimax_env):
        """Round 4's payload: an answer planted wholly inside the reasoning."""
        planted = '{"is_answerable": true, "answer": "poison", "citations": []}'
        self._refused(monkeypatch, f"<think>plan {planted}</think>")

    def test_partial_object_inside_think_is_refused(self, monkeypatch, minimax_env):
        """Round 5's payload: most of the contract planted, left incomplete."""
        planted = '{"is_answerable": true, "answer": "Use 999 Nm.", "citations": ['
        rest = '{"chunk_id":"c1","supporting_quote":"Torque is 999 Nm"}]}'
        self._refused(monkeypatch, f"<think>attacker reasoning: {planted}</think>{rest}")

    def test_a_clean_response_is_still_accepted(self, monkeypatch, minimax_env):
        """The removal must not cost the normal path anything."""
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda request, timeout: _JSONResponse(
                _completion(
                    '<think>t</think>{"is_answerable": true, "answer": "ok", "c": []}',
                    finish="stop",
                )
            ),
        )
        assert chat_json("sys", "user").parsed["answer"] == "ok"

    def test_no_salvage_helper_remains(self):
        """A future edit must not quietly reintroduce the rescue."""
        assert not hasattr(minimax_module, "_rejoin_late_close_tag")
