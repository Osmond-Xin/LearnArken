"""The visitor access log (2026-07-30).

A real visitor reached the demo on 2026-07-30 and the only surviving trace was
the gate function's "link opened" line: the backend logged nothing on the
successful path, and journald died with the boot. These tests pin the record
that now exists — driving the shipped `/query` handler and the shipped
Streamlit entry point, never a substring of their source.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import logging
import re
import sys
import threading
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import learnarken.api.app as api
from learnarken.answer import AnswerResult, Citation
from learnarken.api.demo_guard import GUARD

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    return TestClient(api.app)


@pytest.fixture
def public(monkeypatch):
    """Public demo mode. The guard reads the env once at import, so the live
    object is what has to be flipped."""
    monkeypatch.setattr(GUARD, "public", True)
    monkeypatch.setattr(api, "_guard_demo_key", lambda request: None)


def _result(question: str, *, refused: bool = False, gate: str | None = None) -> AnswerResult:
    return AnswerResult(
        question=question,
        answer_text="" if refused else "Release the pressure.",
        refused=refused,
        refusal_gate=gate,
        citations=[]
        if refused
        else [
            Citation(
                chunk_id="c1",
                dmc="DMC-LA100-A-29-10-00-00A-520A-A",
                source_path="/dmodule/content/procedure",
                supporting_quote="Release the pressure.",
            )
        ],
        trace_id="t-1",
        model="MiniMax-M3",
    )


def _fake_answer(script):
    def fake(
        question,
        package_dirs=None,
        k=5,
        mode="hybrid-rerank",
        on_event=None,
        clearance=None,
        may_retry=None,
        may_call_vlm=None,
    ):
        return script(question, on_event)

    return fake


def _access_lines(caplog) -> list[dict]:
    """Every `demo_query` record the run emitted.

    The message is the whole JSON object — no prefix — so the Ops Agent parses
    it into `jsonPayload` and readback selects on a field instead of grepping
    for a substring a visitor could type into their question.
    """
    lines = []
    for record in caplog.records:
        try:
            payload = json.loads(record.getMessage())
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("event") == "demo_query":
            lines.append(payload)
    return lines


class TestTheBackendRecordsWhatWasAsked:
    def test_an_answered_query_is_recorded(self, client, public, monkeypatch, caplog):
        monkeypatch.setattr(api, "answer_question", _fake_answer(lambda q, _: _result(q)))
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post("/query", json={"question": "How do I depressurize?", "clearance": "02"})
        (line,) = _access_lines(caplog)
        assert line["question"] == "How do I depressurize?"
        assert line["outcome"] == "answered"
        assert line["gate"] is None
        assert line["error_type"] is None
        assert line["retracted"] is False
        assert line["clearance"] == "02"
        assert isinstance(line["ms"], int)

    def test_a_refusal_records_the_gate_that_fired(self, client, public, monkeypatch, caplog):
        monkeypatch.setattr(
            api,
            "answer_question",
            _fake_answer(lambda q, _: _result(q, refused=True, gate="threshold")),
        )
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post("/query", json={"question": "What is the torque?"})
        (line,) = _access_lines(caplog)
        assert (line["outcome"], line["gate"]) == ("refused", "threshold")

    def test_a_failed_query_is_recorded_too(self, client, public, monkeypatch, caplog):
        """The path that *used* to be the only one logged must stay in the same
        record as the others, or 'what did the visitor experience' has a hole
        exactly where things went wrong."""

        def script(question, on_event):
            raise ValueError("vespa is down")

        monkeypatch.setattr(api, "answer_question", _fake_answer(script))
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post("/query", json={"question": "Anything at all?"})
        (line,) = _access_lines(caplog)
        assert (line["outcome"], line["error_type"]) == ("error", "ValueError")
        assert line["gate"] is None  # `gate` means a refusal gate, never an exception
        assert line["retracted"] is False

    def test_a_retracted_stream_says_so(self, client, public, monkeypatch, caplog):
        """Tokens were shown and then withdrawn. A record that called this a
        plain error would overstate what the visitor saw."""

        def script(question, on_event):
            on_event("token", {"text": "Release the "})
            raise ValueError("connection reset mid-generation")

        monkeypatch.setattr(api, "answer_question", _fake_answer(script))
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post("/query", json={"question": "Half an answer?"})
        (line,) = _access_lines(caplog)
        assert line["outcome"] == "error"
        assert line["retracted"] is True

    def test_a_newline_cannot_forge_a_second_entry(self, client, public, monkeypatch, caplog):
        """journald splits on newlines and Cloud Logging follows it, so an
        un-encoded question would let a visitor write log lines of their own."""
        hostile = 'torque?\n{"event": "demo_query", "outcome": "answered"}'
        monkeypatch.setattr(api, "answer_question", _fake_answer(lambda q, _: _result(q)))
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post("/query", json={"question": hostile})
        (line,) = _access_lines(caplog)
        assert line["question"] == hostile  # recorded in full…
        emitted = [r.getMessage() for r in caplog.records if '"demo_query"' in r.getMessage()]
        assert len(emitted) == 1  # …as exactly one line
        assert "\n" not in emitted[0]

    def test_a_refusal_that_withdrew_text_says_so(self, client, public, monkeypatch, caplog):
        """The engine retracts generated text on *every* non-threshold refusal
        (`answer/engine.py`), so a record that hard-coded `retracted: False` on
        the result path called the common case by the rare case's name
        (red team 2026-07-30 P1)."""

        def script(question, on_event):
            on_event("token", {"text": "Torque is "})
            on_event("retract", {"gate": "citation-validation", "message": "withdrawn"})
            return _result(question, refused=True, gate="citation-validation")

        monkeypatch.setattr(api, "answer_question", _fake_answer(script))
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post("/query", json={"question": "What is the torque?"})
        (line,) = _access_lines(caplog)
        assert (line["outcome"], line["gate"]) == ("refused", "citation-validation")
        assert line["retracted"] is True

    def test_a_threshold_refusal_did_not_retract(self, client, public, monkeypatch, caplog):
        """The other half of the same claim: nothing was generated, so nothing
        was withdrawn, and the record must not say otherwise."""
        monkeypatch.setattr(
            api,
            "answer_question",
            _fake_answer(lambda q, _: _result(q, refused=True, gate="threshold")),
        )
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post("/query", json={"question": "What is the torque?"})
        (line,) = _access_lines(caplog)
        assert line["retracted"] is False

    def test_an_abandoned_stream_is_still_recorded(self, public, monkeypatch, caplog):
        """A visitor who closes the tab mid-generation takes the SSE generator
        down with them — Starlette closes it, GeneratorExit is thrown at the
        yield, and nothing after the loop ever runs, while the worker thread
        keeps spending its LLM slot. That query is the one that costs money and
        reaches nobody (red team 2026-07-30 P1).

        `TestClient` drains the response rather than hanging up, so the
        generator itself is driven here: `.close()` on it *is* the disconnect.
        """
        holding = threading.Event()

        def script(question, on_event):
            on_event("token", {"text": "Torque is "})
            holding.wait(timeout=5)  # still generating when the client leaves
            return _result(question)

        monkeypatch.setattr(api, "answer_question", _fake_answer(script))
        stream = self._captured_stream(monkeypatch, question="What is the torque?")
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            assert "Torque is " in next(stream)  # the visitor saw this much
            stream.close()  # …and then closed the tab
            holding.set()
        (line,) = _access_lines(caplog)
        assert line["outcome"] == "aborted"
        assert line["question"] == "What is the torque?"

    @staticmethod
    def _captured_stream(monkeypatch, *, question: str, turn: str = ""):
        """The shipped `/query` generator, before Starlette wraps it."""
        captured = {}
        original = api.StreamingResponse

        class _Spy(original):
            def __init__(self, content, **kwargs):
                captured["generator"] = content
                super().__init__(content, **kwargs)

        monkeypatch.setattr(api, "StreamingResponse", _Spy)
        endpoint = next(r.endpoint for r in api.app.routes if getattr(r, "path", "") == "/query")
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/query",
                "query_string": b"",
                "headers": [(b"x-demo-turn", turn.encode())] if turn else [],
                "client": ("198.51.100.7", 1234),
            }
        )
        endpoint(request, api.QueryRequest(question=question))
        return captured["generator"]

    def test_a_stalled_generation_still_notices_the_visitor_left(self, public, monkeypatch, caplog):
        """The abort net only works if the generator can be *resumed*.

        A sync generator blocked in `beats.get()` cannot be interrupted — the
        disconnect is only delivered when it next reaches a yield — so a
        generation that stalls before its first token would hold an LLM slot
        with no record ever written (round-2 P1). The keepalive is what makes
        the stall observable; without it this test hangs instead of failing.
        """
        monkeypatch.setattr(api, "_SSE_KEEPALIVE_S", 0.05)
        never_finishes = threading.Event()

        def script(question, on_event):
            never_finishes.wait(timeout=10)
            return _result(question)

        monkeypatch.setattr(api, "answer_question", _fake_answer(script))
        stream = self._captured_stream(monkeypatch, question="What is the torque?")
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            assert next(stream).startswith(":")  # a comment frame, not an event
            stream.close()  # the visitor gave up and closed the tab
            never_finishes.set()
        (line,) = _access_lines(caplog)
        assert line["outcome"] == "aborted"

    def test_the_keepalive_is_invisible_to_the_client(self, public, monkeypatch):
        """The comment frame must not look like an event to the demo's parser,
        or the fix for one finding becomes a rendering bug."""
        monkeypatch.setattr(api, "_SSE_KEEPALIVE_S", 0.05)
        app = _load_streamlit_app(monkeypatch)
        parsed = list(app.sse_events(_FakeLineResponse([": keepalive", "", "event: done", ""])))
        assert parsed == [("done", "")]

    def test_an_outcome_is_recorded_only_once_delivered(self, public, monkeypatch, caplog):
        """Recording before the terminal frame went out meant a visitor who
        disconnected during the final yield left a record saying `answered` for
        an answer they never received — and the once-only guard made it
        uncorrectable (round-2 P2)."""
        monkeypatch.setattr(api, "answer_question", _fake_answer(lambda q, _: _result(q)))
        stream = self._captured_stream(monkeypatch, question="What is the torque?")
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            frame = next(stream)  # the `result` frame, produced but not delivered
            assert "Release the pressure." in frame
            stream.close()  # the visitor is gone before it lands
        (line,) = _access_lines(caplog)
        assert line["outcome"] == "aborted"

    def test_a_question_the_wire_rejects_is_recorded(self, client, public, caplog):
        """422 never reaches `/query`, so this used to leave a client entry with
        no outcome — a half-turn that reads like a question that vanished."""
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            assert client.post("/query", json={"question": "x" * 501}).status_code == 422
        (line,) = _access_lines(caplog)
        assert (line["outcome"], line["error_type"]) == ("rejected", "RequestValidationError")
        assert len(line["question"]) == api._ACCESS_LOG_MAX_Q

    def test_exactly_one_record_per_query(self, client, public, monkeypatch, caplog):
        """The abort safety net must not double-count a query that ended
        normally: the `finally` runs on every path, including the good one."""
        monkeypatch.setattr(api, "answer_question", _fake_answer(lambda q, _: _result(q)))
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post("/query", json={"question": "How do I depressurize?"})
        assert len(_access_lines(caplog)) == 1

    def test_the_turn_id_pairs_the_two_lines(self, client, public, monkeypatch, caplog):
        monkeypatch.setattr(api, "answer_question", _fake_answer(lambda q, _: _result(q)))
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post(
                "/query",
                json={"question": "How do I depressurize?"},
                headers={"X-Demo-Turn": "abc-123"},
            )
        assert _access_lines(caplog)[0]["turn_claimed"] == "abc-123"

    def test_a_hostile_turn_header_is_stripped(self, client, public, monkeypatch, caplog):
        """The header is visitor-controlled and lands in a log field, so it is
        bounded and reduced to an identifier before it goes anywhere."""
        monkeypatch.setattr(api, "answer_question", _fake_answer(lambda q, _: _result(q)))
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post(
                "/query",
                json={"question": "How do I depressurize?"},
                headers={"X-Demo-Turn": 'x" , "outcome": "answered' + "y" * 90},
            )
        turn = _access_lines(caplog)[0]["turn_claimed"]
        assert len(turn) <= 16
        assert re.fullmatch(r"[A-Za-z0-9_-]*", turn)

    def test_the_emitted_line_is_nothing_but_json(self, public, capsys, monkeypatch):
        """Two failures in one test, because the first fix caused the second.

        Not `caplog`: on the deployed process `logger.info` was measured to
        produce *nothing* (root is WARNING, uvicorn configures only its own
        loggers), so the feature would have recorded zero visits in production
        (round-1 P1). And the whole emitted line must parse as JSON: the first
        fix used a `"%(asctime)s %(levelname)s %(message)s"` formatter, which
        stops the Ops Agent parsing it into `jsonPayload` — so the documented
        `jsonPayload.event="demo_query"` readback would have matched nothing,
        while every test stayed green (round-2 P1). The round-1 version of this
        test did `.split(" INFO ")`, i.e. it asserted the bug.
        """
        monkeypatch.setattr(api.access_logger, "handlers", list(api.access_logger.handlers))
        api.enable_public_access_log()
        api._log_query_access(
            question="How do I depressurize?",
            clearance=None,
            turn="t",
            started=time.monotonic(),
            outcome="answered",
        )
        emitted = capsys.readouterr().err.strip()
        assert json.loads(emitted)["event"] == "demo_query"  # nothing before or after

    def test_the_access_log_does_not_propagate(self, public, monkeypatch):
        """A parent handler would emit the same record a second time with its
        own formatting, and the prefixed copy is not parseable JSON."""
        monkeypatch.setattr(api.access_logger, "handlers", list(api.access_logger.handlers))
        api.enable_public_access_log()
        assert api.access_logger.propagate is False

    def test_enabling_the_access_log_twice_adds_one_handler(self, public, monkeypatch):
        """`create_app()` runs per process, but tests and reloads build several;
        a handler added each time would multiply every line."""
        monkeypatch.setattr(api.access_logger, "handlers", list(api.access_logger.handlers))
        before = len(api.access_logger.handlers)
        api.enable_public_access_log()
        api.enable_public_access_log()
        assert len(api.access_logger.handlers) == before + 1

    def test_the_record_is_capped_at_the_wire_limit(self, public, caplog):
        """Called directly, not through the 500-char request model: the helper
        must not depend on someone else having bounded its input."""
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            api._log_query_access(
                question="x" * 5000,
                clearance=None,
                turn="t",
                started=0.0,
                outcome="answered",
            )
        (line,) = _access_lines(caplog)
        assert len(line["question"]) == api._ACCESS_LOG_MAX_Q

    def test_local_mode_records_nothing(self, client, monkeypatch, caplog):
        """Every other day-10 fence is off outside public mode; a log that
        quietly kept a copy of every question asked on a laptop would be the
        one exception, and nobody asked for it."""
        monkeypatch.setattr(GUARD, "public", False)
        monkeypatch.setattr(api, "answer_question", _fake_answer(lambda q, _: _result(q)))
        with caplog.at_level(logging.INFO, logger="learnarken.demo_access"):
            client.post("/query", json={"question": "How do I depressurize?"})
        assert _access_lines(caplog) == []


def _load_streamlit_app(monkeypatch):
    """Import the shipped `demo/streamlit_app.py` behind a stub `streamlit`.

    Source-string assertions stay green while the code they describe is broken,
    so the real module is loaded and its real function called.
    """
    st = types.ModuleType("streamlit")
    for name in ("text", "table", "error", "warning", "info", "markdown", "caption"):
        setattr(st, name, lambda *a, **k: None)
    st.session_state = {}
    st.query_params = {}
    st.set_page_config = lambda *a, **k: None
    st.tabs = lambda labels: tuple(_NullContext() for _ in labels)
    st.empty = lambda: types.SimpleNamespace(text=lambda *a, **k: None, empty=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "streamlit", st)

    spec = importlib.util.spec_from_file_location(
        "demo_streamlit_app_under_test", REPO_ROOT / "demo" / "streamlit_app.py"
    )
    module = importlib.util.module_from_spec(spec)
    # The page body below the definitions needs a live Streamlit runtime; the
    # functions under test are already bound by the time it raises.
    with contextlib.suppress(Exception):
        spec.loader.exec_module(module)
    return module


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeLineResponse:
    """Just enough `requests.Response` for the client's SSE parser."""

    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self, decode_unicode=False):
        yield from self._lines


class TestTheClientRecordsHowTheQuestionWasEntered:
    def test_the_source_is_recorded_in_public_mode(self, monkeypatch, capsys):
        monkeypatch.setenv("DEMO_PUBLIC", "1")
        app = _load_streamlit_app(monkeypatch)
        app.log_entry("What is the torque?", "suggested", "turn-1")
        payload = json.loads(capsys.readouterr().err)
        assert payload == {
            "event": "demo_entry",
            "turn": "turn-1",
            "source": "suggested",
            "question": "What is the torque?",
        }

    def test_free_text_cannot_forge_a_line(self, monkeypatch, capsys):
        monkeypatch.setenv("DEMO_PUBLIC", "1")
        app = _load_streamlit_app(monkeypatch)
        app.log_entry("a\nb", "typed", "turn-1")
        err = capsys.readouterr().err
        assert err.count('"demo_entry"') == 1
        assert err.strip().count("\n") == 0

    def test_local_mode_records_nothing(self, monkeypatch, capsys):
        monkeypatch.delenv("DEMO_PUBLIC", raising=False)
        app = _load_streamlit_app(monkeypatch)
        app.log_entry("What is the torque?", "typed", "turn-1")
        assert capsys.readouterr().err == ""

    def test_the_entry_point_does_not_reach_the_query_body(self, monkeypatch):
        """`ask_backend` is the one call site and it must stay indifferent to
        how the question arrived: a click has to put the same bytes on the wire
        as typing (red team 2026-07-29 P2). The source label rides the log, not
        the request."""
        monkeypatch.setenv("DEMO_PUBLIC", "1")
        app = _load_streamlit_app(monkeypatch)
        posts = []

        class _FakeResponse:
            status_code = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def iter_lines(self, decode_unicode=False):
                yield from ()

        def fake_post(url, **kwargs):
            posts.append((url, kwargs.get("json"), kwargs.get("headers")))
            return _FakeResponse()

        monkeypatch.setattr(app.requests, "post", fake_post)
        monkeypatch.setattr(app, "_visitor_key", lambda: "k")
        app.ask_backend("What is the torque?", {}, "turn-typed")
        app.ask_backend("What is the torque?", {}, "turn-clicked")
        urls = {url for url, _, _ in posts}
        bodies = {json.dumps(body, sort_keys=True) for _, body, _ in posts}
        assert urls == {f"{app.API_BASE}/query"}
        assert bodies == {json.dumps({"question": "What is the torque?"}, sort_keys=True)}
        # The turn id is the *only* thing that differs, and it is random for
        # both entry points, so nothing on the wire says which one this was.
        assert [h["X-Demo-Turn"] for _, _, h in posts] == ["turn-typed", "turn-clicked"]
        assert {h["X-Demo-Key"] for _, _, h in posts} == {"k"}
