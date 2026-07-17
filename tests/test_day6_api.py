"""Day 6 hermetic tests: the FastAPI upload/query surface (engine and
services mocked — no Vespa/Neo4j/LLM/models), the engine's SSE event
emission, and the frontend's dumb-client purity. Live end-to-end runs are
manual via `make demo`."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

import learnarken.answer.engine as engine
import learnarken.api.app as api
from learnarken.answer import AnswerResult, Citation, answer_question
from learnarken.chunking.base import Chunk
from learnarken.graph import GraphFacts
from learnarken.llm import LLMError
from learnarken.llm.minimax import ChatResult
from learnarken.vespa import VespaError

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- helpers


def _events(sse_text: str) -> list[tuple[str, dict]]:
    out = []
    for block in sse_text.strip().split("\n\n"):
        event, data = None, ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        out.append((event, json.loads(data) if data else {}))
    return out


def _answered(question: str) -> AnswerResult:
    return AnswerResult(
        question=question,
        answer_text="Release the pressure.",
        refused=False,
        citations=[
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


def _refusal(question: str, gate: str) -> AnswerResult:
    return AnswerResult(
        question=question,
        answer_text=engine.PLACEHOLDER,
        refused=True,
        refusal_gate=gate,
        trace_id="t-1",
    )


@pytest.fixture
def client():
    return TestClient(api.app)


@pytest.fixture
def upload_dir(monkeypatch, tmp_path):
    target = tmp_path / "package-upload"
    monkeypatch.setattr(api, "UPLOAD_PACKAGE", target)
    return target


class _Report:
    """Stands in for ValidationReport: the API reads error_count + to_dict."""

    def __init__(self, error_count: int = 0, findings: list | None = None):
        self.error_count = error_count
        self.findings = findings or []

    def to_dict(self):
        return {"error_count": self.error_count, "findings": self.findings}


class _Package:
    """Stands in for PackageModel: the API reads data_modules[*].file."""

    def __init__(self, *files: str):
        self.data_modules = [SimpleNamespace(file=f) for f in files]


# ---------------------------------------------------------------- /upload


class TestUploadEnvelope:
    def test_path_traversal_filename_rejected(self, client, upload_dir):
        resp = client.post("/upload", files={"file": ("../../evil.xml", b"<x/>")})
        # starlette's multipart parser may already 422 a path-y filename;
        # either way it must never reach the filesystem.
        assert resp.status_code in (400, 422)

    def test_non_xml_extension_rejected(self, client, upload_dir):
        resp = client.post("/upload", files={"file": ("notes.txt", b"hi")})
        assert resp.status_code == 400

    def test_dotfile_rejected(self, client, upload_dir):
        resp = client.post("/upload", files={"file": (".hidden.xml", b"<x/>")})
        assert resp.status_code == 400

    def test_non_dmc_name_rejected(self, client, upload_dir):
        # The scanner only recognizes DMC-*.xml; anything else would be a
        # silently ignored no-op claiming "ingested" (found live 2026-07-17).
        resp = client.post("/upload", files={"file": ("broken.xml", b"<x/>")})
        assert resp.status_code == 400
        assert "DMC-" in resp.json()["detail"]

    def test_oversize_rejected(self, client, upload_dir):
        blob = b"x" * (api.MAX_UPLOAD_BYTES + 1)
        resp = client.post("/upload", files={"file": ("DMC-big.xml", blob)})
        assert resp.status_code == 413

    def test_non_utf8_rejected(self, client, upload_dir):
        resp = client.post("/upload", files={"file": ("DMC-bad.xml", b"\xff\xfe<x/>")})
        assert resp.status_code == 400

    def test_oversize_content_length_rejected_pre_parse(self, client, upload_dir):
        # A declared Content-Length over the cap is refused before the body is
        # spooled (red-team day6 #2). No real large body is sent.
        huge = str(api.MAX_UPLOAD_BYTES + api._MULTIPART_SLACK + 1)
        resp = client.post(
            "/upload",
            files={"file": ("DMC-dm.xml", b"<x/>")},
            headers={"content-length": huge},
        )
        assert resp.status_code == 413


class TestCsrf:
    def test_foreign_origin_refused_on_upload(self, client, upload_dir):
        resp = client.post(
            "/upload",
            files={"file": ("DMC-dm.xml", b"<x/>")},
            headers={"origin": "https://evil.example"},
        )
        assert resp.status_code == 403

    def test_foreign_origin_refused_on_query(self, client):
        resp = client.post(
            "/query", json={"question": "anything?"}, headers={"origin": "https://evil.example"}
        )
        assert resp.status_code == 403

    def test_loopback_origin_allowed(self, client, upload_dir, monkeypatch):
        monkeypatch.setattr(api, "analyze_package", lambda pkg: (_Report(), _Package("DMC-dm.xml")))
        monkeypatch.setattr(api, "index_package", lambda packages, strategy: 1)
        resp = client.post(
            "/upload",
            files={"file": ("DMC-dm.xml", b"<dmodule/>")},
            headers={"origin": "http://127.0.0.1:8100"},
        )
        assert resp.status_code == 200

    def test_no_origin_allowed(self, client):
        # Server-side clients (Streamlit `requests`, curl) send no Origin.
        assert client.post("/query", json={"question": "ab"}).status_code == 422  # not 403


class TestUploadOutcomes:
    def test_validation_failure_rejected_and_removed(self, client, upload_dir, monkeypatch):
        findings = [
            {
                "layer": "L2",
                "rule_id": "BREX-002",
                "severity": "error",
                "file": "dm.xml",
                "message": "boom",
            }
        ]
        monkeypatch.setattr(
            api,
            "analyze_package",
            lambda pkg: (_Report(error_count=1, findings=findings), _Package("DMC-dm.xml")),
        )
        resp = client.post("/upload", files={"file": ("DMC-dm.xml", b"<dmodule/>")})
        assert resp.status_code == 422
        assert resp.json()["status"] == "rejected"
        assert resp.json()["report"]["findings"] == findings
        assert not (upload_dir / "DMC-dm.xml").exists()  # never keeps a failed module

    def test_scanner_ignored_file_rejected(self, client, upload_dir, monkeypatch):
        # Validation "passes" but the scanner never parsed the file: must be
        # rejected and removed, never reported as ingested (live find 2026-07-17).
        monkeypatch.setattr(
            api, "analyze_package", lambda pkg: (_Report(), _Package("DMC-other.xml"))
        )
        resp = client.post("/upload", files={"file": ("DMC-dm.xml", b"not a dm")})
        assert resp.status_code == 422
        assert resp.json()["status"] == "rejected"
        assert "not recognized" in resp.json()["message"]
        assert not (upload_dir / "DMC-dm.xml").exists()

    def test_clean_module_ingested(self, client, upload_dir, monkeypatch):
        monkeypatch.setattr(api, "analyze_package", lambda pkg: (_Report(), _Package("DMC-dm.xml")))
        seen = {}

        def fake_index(packages, strategy):
            seen["packages"], seen["strategy"] = packages, strategy
            return 42

        monkeypatch.setattr(api, "index_package", fake_index)
        resp = client.post("/upload", files={"file": ("DMC-dm.xml", b"<dmodule/>")})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ingested" and body["indexed_chunks"] == 42
        assert (upload_dir / "DMC-dm.xml").exists()  # swapped in after index
        assert seen["strategy"] == "structure"
        # Indexed from a staging dir, but the basename (engine scope identity)
        # must stay "package-upload".
        assert Path(seen["packages"][-1]).name == "package-upload"
        assert len(seen["packages"]) == 3

    def test_index_failure_fails_closed_and_removes(self, client, upload_dir, monkeypatch):
        monkeypatch.setattr(api, "analyze_package", lambda pkg: (_Report(), _Package("DMC-dm.xml")))

        def boom(packages, strategy):
            raise VespaError("feed refused")

        monkeypatch.setattr(api, "index_package", boom)
        resp = client.post("/upload", files={"file": ("DMC-dm.xml", b"<dmodule/>")})
        assert resp.status_code == 503
        assert resp.json()["status"] == "index_failed"
        assert not (upload_dir / "DMC-dm.xml").exists()

    def test_failed_replacement_preserves_prior_valid_module(self, client, upload_dir, monkeypatch):
        # Seed an already-ingested module, then re-upload the same name with
        # content that fails validation: the prior valid file must survive
        # (red-team day6 #1 — replacement must be transactional).
        upload_dir.mkdir(parents=True)
        good = b"<dmodule>original-valid</dmodule>"
        (upload_dir / "DMC-dm.xml").write_bytes(good)

        def analyze(pkg):
            # The staged copy contains the candidate bytes; fail it.
            return _Report(error_count=1, findings=[{"severity": "error"}]), _Package("DMC-dm.xml")

        monkeypatch.setattr(api, "analyze_package", analyze)
        resp = client.post("/upload", files={"file": ("DMC-dm.xml", b"<broken")})
        assert resp.status_code == 422
        assert (upload_dir / "DMC-dm.xml").read_bytes() == good  # untouched


# ---------------------------------------------------------------- /query


class TestQuerySSE:
    def _fake_answer(self, script):
        """script(on_event) -> AnswerResult, wired as answer_question."""

        def fake(question, package_dirs=None, k=5, mode="hybrid-rerank", on_event=None):
            return script(question, on_event)

        return fake

    def test_question_bounds(self, client):
        assert client.post("/query", json={"question": "ab"}).status_code == 422
        assert client.post("/query", json={"question": "x" * 501}).status_code == 422

    def test_answer_stream_event_order(self, client, monkeypatch):
        def script(question, on_event):
            on_event("status", {"stage": "retrieval"})
            on_event("status", {"stage": "rerank"})
            on_event("status", {"stage": "generating"})
            on_event("token", {"text": "Release the "})
            on_event("token", {"text": "pressure."})
            return _answered(question)

        monkeypatch.setattr(api, "answer_question", self._fake_answer(script))
        resp = client.post("/query", json={"question": "How do I depressurize?"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _events(resp.text)
        kinds = [k for k, _ in events]
        assert kinds == ["status", "status", "status", "token", "token", "result", "done"]
        tokens = "".join(d["text"] for k, d in events if k == "token")
        result = dict(events)["result"]
        assert tokens == result["answer_text"] == "Release the pressure."
        assert result["citations"][0]["chunk_id"] == "c1"

    def test_retraction_withdraws_streamed_tokens(self, client, monkeypatch):
        def script(question, on_event):
            on_event("status", {"stage": "generating"})
            on_event("token", {"text": "The torque is 999 Nm"})  # ungrounded
            on_event(
                "retract",
                {"gate": "citation-validation", "message": "retracted"},
            )
            return _refusal(question, "citation-validation")

        monkeypatch.setattr(api, "answer_question", self._fake_answer(script))
        events = _events(client.post("/query", json={"question": "torque?"}).text)
        kinds = [k for k, _ in events]
        assert kinds.index("token") < kinds.index("retract") < kinds.index("result")
        result = dict(events)["result"]
        assert result["refused"] is True
        assert result["refusal_gate"] == "citation-validation"
        assert result["answer_text"] == engine.PLACEHOLDER

    def test_threshold_refusal_streams_nothing(self, client, monkeypatch):
        def script(question, on_event):
            on_event("status", {"stage": "retrieval"})
            on_event("status", {"stage": "rerank"})
            return _refusal(question, "threshold")

        monkeypatch.setattr(api, "answer_question", self._fake_answer(script))
        events = _events(client.post("/query", json={"question": "irrelevant?"}).text)
        kinds = [k for k, _ in events]
        assert "token" not in kinds and "retract" not in kinds
        assert dict(events)["result"]["refusal_gate"] == "threshold"

    def test_service_failure_is_error_event(self, client, monkeypatch):
        def script(question, on_event):
            raise LLMError("MiniMax chat unreachable (3 attempts)")

        monkeypatch.setattr(api, "answer_question", self._fake_answer(script))
        events = _events(client.post("/query", json={"question": "anything?"}).text)
        kinds = [k for k, _ in events]
        assert "result" not in kinds
        assert "retract" not in kinds  # no tokens were shown: nothing to withdraw
        assert dict(events)["error"]["message"].startswith("LLMError")
        assert kinds[-1] == "done"

    def test_mid_stream_transport_failure_retracts_before_error(self, client, monkeypatch):
        # Tokens shown, then the stream aborts: a retract must precede the
        # error so non-Streamlit clients withdraw the unverified text
        # (red-team day6 #3).
        def script(question, on_event):
            on_event("status", {"stage": "generating"})
            on_event("token", {"text": "Open valve "})
            on_event("token", {"text": "3 and"})
            raise LLMError("connection reset mid-stream")

        monkeypatch.setattr(api, "answer_question", self._fake_answer(script))
        events = _events(client.post("/query", json={"question": "valve?"}).text)
        kinds = [k for k, _ in events]
        assert "token" in kinds
        assert kinds.index("retract") < kinds.index("error")
        assert dict(events)["retract"]["gate"] == "transport"
        assert "result" not in kinds and kinds[-1] == "done"

    def test_unexpected_failure_is_opaque(self, client, monkeypatch):
        def script(question, on_event):
            raise RuntimeError("secret internal detail")

        monkeypatch.setattr(api, "answer_question", self._fake_answer(script))
        resp = client.post("/query", json={"question": "anything?"})
        assert "secret" not in resp.text
        assert dict(_events(resp.text))["error"]["message"] == "internal error (fail closed)"


# ---------------------------------------------------------------- /health


class TestHealth:
    def test_degraded_when_a_service_is_down(self, client, monkeypatch):
        monkeypatch.setattr(api.vespa, "is_up", lambda: True)
        monkeypatch.setattr(api.graph, "is_up", lambda: False)
        monkeypatch.setattr(api, "load_minimax_config", lambda: {"ok": 1})
        monkeypatch.setattr(api, "load_threshold", lambda: 0.5)
        body = client.get("/health").json()
        assert body["status"] == "degraded"
        assert body["services"]["neo4j"]["ok"] is False
        assert body["services"]["vespa"]["ok"] is True

    def test_ok_when_all_up(self, client, monkeypatch):
        monkeypatch.setattr(api.vespa, "is_up", lambda: True)
        monkeypatch.setattr(api.graph, "is_up", lambda: True)
        monkeypatch.setattr(api, "load_minimax_config", lambda: {"ok": 1})
        monkeypatch.setattr(api, "load_threshold", lambda: 0.5)
        assert client.get("/health").json()["status"] == "ok"


# ------------------------------------------------- engine event emission


def _chunk_obj(cid: str, text: str) -> Chunk:
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


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Hermetic engine wiring (same shape as test_day5_answer.wired)."""
    monkeypatch.chdir(tmp_path)  # traces land in tmp, not the repo
    chunks = [_chunk_obj("c1", "Release the pressure."), _chunk_obj("c2", "Remove the bolts.")]
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


def _fake_stream(parsed: dict):
    """Stands in for chat_json_stream: replays the raw M3 stream in deltas."""
    raw = "<think>reasoning</think>" + json.dumps(parsed)

    def fake(system, user, *, on_delta, **kwargs):
        for i in range(0, len(raw), 7):
            on_delta(raw[i : i + 7])
        return ChatResult(
            parsed=parsed,
            raw_content=raw,
            model="MiniMax-M3",
            usage={},
            request_payload={"messages": [], "stream": True},
        )

    return fake


class TestEngineEvents:
    def _run(self, monkeypatch, parsed: dict):
        monkeypatch.setattr(engine, "chat_json_stream", _fake_stream(parsed))
        events: list[tuple[str, dict]] = []
        result = answer_question(
            "How do I remove the pump?", on_event=lambda k, d: events.append((k, d))
        )
        return events, result

    def test_streamed_tokens_match_answer(self, monkeypatch, wired):
        events, result = self._run(
            monkeypatch,
            {
                "is_answerable": True,
                "answer": "Release the pressure.",
                "citations": [{"chunk_id": "c1", "supporting_quote": "Release the pressure."}],
            },
        )
        kinds = [k for k, _ in events]
        assert kinds[:3] == ["status", "status", "status"]
        assert [d["stage"] for k, d in events if k == "status"] == [
            "retrieval",
            "rerank",
            "generating",
        ]
        streamed = "".join(d["text"] for k, d in events if k == "token")
        assert streamed == "Release the pressure." == result.answer_text
        assert "retract" not in kinds and result.refused is False

    def test_failed_citation_gate_emits_retract(self, monkeypatch, wired):
        events, result = self._run(
            monkeypatch,
            {
                "is_answerable": True,
                "answer": "The torque is 999 Nm.",
                "citations": [{"chunk_id": "c1", "supporting_quote": "torque is 999"}],
            },
        )
        kinds = [k for k, _ in events]
        assert "token" in kinds  # unverified text really was streamed first
        retracts = [d for k, d in events if k == "retract"]
        assert len(retracts) == 1 and retracts[0]["gate"] == "citation-validation"
        assert result.refused and result.refusal_gate == "citation-validation"

    def test_threshold_refusal_never_streams_or_retracts(self, monkeypatch, wired):
        import learnarken.retrieval.hybrid as hybrid

        monkeypatch.setattr(hybrid, "rerank_scored", lambda q, d, k=10: [(d[0], 0.01)] if d else [])
        called = []
        monkeypatch.setattr(engine, "chat_json_stream", lambda *a, **kw: called.append(1))
        events: list[tuple[str, dict]] = []
        result = answer_question("Unrelated?", on_event=lambda k, d: events.append((k, d)))
        kinds = [k for k, _ in events]
        assert result.refusal_gate == "threshold"
        assert "token" not in kinds and "retract" not in kinds and not called
        assert [d["stage"] for k, d in events if k == "status"] == ["retrieval", "rerank"]


# ------------------------------------------------- frontend purity


class TestFrontendPurity:
    def test_streamlit_app_never_imports_learnarken(self):
        source = (REPO_ROOT / "demo" / "streamlit_app.py").read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+learnarken", source, re.MULTILINE), (
            "the Streamlit frontend must stay a dumb client (SPEC day6 decision 1)"
        )

    def test_frontend_never_renders_raw_html(self):
        source = (REPO_ROOT / "demo" / "streamlit_app.py").read_text(encoding="utf-8")
        assert not re.search(r"unsafe_allow_html\s*=\s*True", source)
