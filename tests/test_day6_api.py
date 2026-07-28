"""Day 6 hermetic tests: the FastAPI upload/query surface (engine and
services mocked — no Vespa/Neo4j/LLM/models), the engine's SSE event
emission, and the frontend's dumb-client purity. Live end-to-end runs are
manual via `make demo`."""

import ast
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


def _frontend_dict(name: str) -> dict:
    """Read a module-level dict literal out of the Streamlit app without
    importing it — the frontend needs streamlit installed, and importing it
    would also run the page."""
    tree = ast.parse((REPO_ROOT / "demo" / "streamlit_app.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in the frontend")


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

        def fake(
            question, package_dirs=None, k=5, mode="hybrid-rerank", on_event=None, clearance=None
        ):
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
    monkeypatch.setattr(engine, "corpus_chunks", lambda pkg, strategy: list(chunks))
    monkeypatch.setattr(engine, "verify_corpus", lambda c, s: None)
    monkeypatch.setattr(engine, "load_threshold", lambda: 0.5)
    monkeypatch.setattr(
        engine,
        "_candidates",
        lambda question, c, mode, clearance=None: [
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

    def test_every_gate_the_backend_emits_is_labelled(self):
        """A gate the engine can refuse at must be nameable on screen. The
        frontend cannot import learnarken, so the two tables are kept in step
        here instead — `figure-out-of-description` had drifted out and rendered
        as '?'."""
        from learnarken.refusal import RESOLUTIONS

        labels = _frontend_dict("GATE_LABELS")
        missing = sorted(set(RESOLUTIONS) - set(labels))
        assert not missing, f"gates the demo UI cannot name: {missing}"
        # The API's own retract-on-transport-failure gate is not in RESOLUTIONS
        # (no RefusalAction is built for it) but does reach the screen.
        assert "transport" in labels

    def test_frontend_renders_the_routed_refusal(self):
        """Arken pillar 3 is three parts; the UI used to show only the gate,
        leaving `what would resolve it` / `who should act` on the wire."""
        source = (REPO_ROOT / "demo" / "streamlit_app.py").read_text(encoding="utf-8")
        assert "what_would_resolve" in source
        assert "owner_reason" in source

    def test_rendering_is_gated_on_the_single_classifier(self):
        """Direct field reads in `render_answer` are only safe because
        `classify_turn` validated the payload first. If a future edit renders
        without asking it, that guarantee is gone (red-team 2026-07-27 P2)."""
        source = (REPO_ROOT / "demo" / "streamlit_app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        render = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_answer"
        )
        called = {
            n.func.id
            for n in ast.walk(render)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "classify_turn" in called


class _FakeSt:
    """Records the Streamlit calls the frontend makes, so a test can assert what
    reached the operator's screen and through which renderer."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args[0] if args else ""))

        return record

    def kinds(self) -> list[str]:
        return [name for name, _ in self.calls]

    def text_of(self, kind: str) -> str:
        return " ".join(str(a) for name, a in self.calls if name == kind)


def _frontend_namespace(fake: _FakeSt | None = None) -> dict:
    """Load the shipped frontend's pure logic, with `st` faked.

    The module cannot simply be imported: it needs streamlit installed, and
    importing it would run the page. Testing a copy of the logic would let the
    shipped code drift away from the test (red-team 2026-07-27 P2), so the real
    definitions are lifted out of the source file.
    """
    source = (REPO_ROOT / "demo" / "streamlit_app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {
        "_filled",
        "_is_answered",
        "_is_refusal",
        "classify_turn",
        "gate_label",
        "record_event",
        "render_answer",
        "visible_len",
    }
    body = [
        n
        for n in tree.body
        if (isinstance(n, ast.FunctionDef) and n.name in wanted)
        or (
            isinstance(n, ast.Assign)
            and any(
                getattr(t, "id", None) in ("GATE_LABELS", "CITATION_FIELDS", "_INVISIBLE")
                for t in n.targets
            )
        )
    ]
    namespace: dict = {"st": fake if fake is not None else _FakeSt()}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<frontend>", "exec"), namespace)
    return namespace


def _frontend_render(entry: dict) -> _FakeSt:
    """Run the shipped `render_answer` against a fake `st` and report the calls."""
    fake = _FakeSt()
    _frontend_namespace(fake)["render_answer"](entry)
    return fake


def _citation(**overrides) -> dict:
    c = {
        "chunk_id": "106807baae8e3f1c",
        "dmc": "DMC-LA100-A-29-10-00-00A-520A-A",
        "source_path": "/dmodule/content",
        "supporting_quote": "Release the pressure.",
    }
    c.update(overrides)
    return c


def _answered_result(**overrides) -> dict:
    result = {
        "refused": False,
        "answer_text": "Release the pressure.",
        "trace_id": "t-1",
        "model": "MiniMax-M3",
        "citations": [
            {
                "chunk_id": "c1",
                "dmc": "DMC-LA100-A-29-10-00-00A-520A-A",
                "source_path": "/dmodule/content",
                "supporting_quote": "Release the pressure.",
            }
        ],
    }
    result.update(overrides)
    return result


def _refusal_result(**overrides) -> dict:
    result = {
        "refused": True,
        "answer_text": "I don't know — no answer was found in the indexed corpus.",
        "refusal_gate": "llm",
        "trace_id": "t-2",
        "action": {
            "gate": "llm",
            "why": "refused at the llm gate",
            "what_would_resolve": "supply a data module that states the answer",
            "owner": None,
            "owner_reason": "the question names no data module",
        },
    }
    result.update(overrides)
    return result


class TestFrontendFailsClosedOnBadResults:
    """Reading every wire field defensively must not turn a crash into a false
    success (red-team 2026-07-27 P1)."""

    def test_a_complete_answer_renders_verified(self):
        fake = _frontend_render({"result": _answered_result()})
        assert "Citations verified" in fake.text_of("caption")
        assert "table" in fake.kinds()

    def test_the_xpath_gets_a_row_of_its_own(self):
        """An XPath contains no spaces, so it cannot wrap. Sharing a four-column
        table with a long quote clipped it mid-path — and the XPath *is* the
        provenance claim. One table per citation, one row per field, so the
        value column has the width to hold it.

        Measured on this corpus: the longest source_path is 73 characters, which
        is the one the README GIF shows.
        """
        long_path = "/dmodule/content/procedure/preliminaryRqmts/reqSafety/safetyRqmts/warning"
        fake = _frontend_render(
            {"result": _answered_result(citations=[_citation(source_path=long_path)])}
        )
        rows = [args for kind, args in fake.calls if kind == "table"]
        assert len(rows) == 1, "one table per citation"
        by_field = {r["Evidence"]: r["Value"] for r in rows[0]}
        assert by_field["XPath"] == long_path, "the XPath must survive whole"
        assert set(by_field) == {"chunk_id", "DMC", "XPath", "Supporting quote"}

    def test_the_corpus_cannot_produce_an_unshowable_xpath(self):
        """The layout gives the XPath a column of its own, but `st.table` still
        will not break a string with no spaces — so the fix holds only while
        paths stay within the width that column has.

        This pins the assumption rather than trusting it: source paths come from
        `tree.getpath()`, so a deeply nested or heavily indexed module could grow
        one past what fits. If this fails, the display needs a wrapping fallback,
        not a bigger number (red-team 2026-07-27 P3).
        """
        from learnarken.chunking import chunk_package

        paths = [
            c.source_path
            for pkg in ("samples/package-a", "samples/package-c")
            for c in chunk_package(str(REPO_ROOT / pkg), strategy="structure")
        ]
        longest = max(paths, key=len)
        assert len(longest) <= 120, f"XPath too long to display whole: {longest}"

    def test_model_name_is_stripped_before_a_markdown_renderer(self):
        """`model` comes off the wire and `st.caption` renders markdown. The
        name may survive as inert text; the link syntax may not."""
        fake = _frontend_render(
            {"result": _answered_result(model="[pwn](https://attacker.example)")}
        )
        caption = fake.text_of("caption")
        assert not any(ch in caption for ch in "[]()/:"), caption
        assert "Citations verified" in caption

    def test_each_citation_gets_its_own_table(self):
        fake = _frontend_render(
            {
                "result": _answered_result(
                    citations=[_citation(chunk_id="c1"), _citation(chunk_id="c2")]
                )
            }
        )
        assert len([k for k, _ in fake.calls if k == "table"]) == 2

    def test_a_complete_refusal_renders_its_routing(self):
        fake = _frontend_render({"result": _refusal_result()})
        assert "Refused" in fake.text_of("info")
        assert "What would resolve it" in fake.text_of("text")
        assert "Who should act" in fake.text_of("text")

    @pytest.mark.parametrize(
        ("name", "entry"),
        [
            ("no result at all", {}),
            ("empty result", {"result": {}}),
            ("result is not a dict", {"result": "boom"}),
            ("answer without the refused flag", {"result": {"answer_text": "Release the brake"}}),
            ("answer with no citations", {"result": _answered_result(citations=[])}),
            ("answer with an empty citation", {"result": _answered_result(citations=[{}])}),
            (
                "citation missing its quote",
                {
                    "result": _answered_result(
                        citations=[{"chunk_id": "c", "dmc": "d", "source_path": "/x"}]
                    )
                },
            ),
            ("answer with a blank body", {"result": _answered_result(answer_text="   ")}),
            ("answer with no trace", {"result": _answered_result(trace_id="")}),
            ("bare refusal", {"result": {"refused": True}}),
            ("refusal with no action", {"result": _refusal_result(action=None)}),
            ("refusal with no gate", {"result": _refusal_result(refusal_gate="")}),
            ("error event with no message", {"error": ""}),
            (
                "retracted, then answered anyway",
                {"retracted": True, "gate": "citation-validation", "result": _answered_result()},
            ),
        ],
    )
    def test_incomplete_turns_fail_closed(self, name, entry):
        fake = _frontend_render(entry)
        assert "error" in fake.kinds(), f"{name}: should have rendered a fail-closed error"
        assert "Citations verified" not in fake.text_of("caption"), f"{name}: rendered as verified"
        assert "table" not in fake.kinds(), f"{name}: rendered an evidence table"

    def test_retraction_with_no_streamed_text_says_so(self):
        """The APU take fires the retraction with `token: 0`: the gate wins
        before any answer text is shown. Saying "the text a moment ago has been
        withdrawn" would describe an event the viewer never saw."""
        fake = _frontend_render(
            {"retracted": True, "gate": "llm", "streamed_chars": 0, "result": _refusal_result()}
        )
        said = fake.text_of("text")
        assert "nothing to withdraw" in said
        assert "shown a moment ago" not in said

    def test_retraction_after_visible_text_says_that_instead(self):
        fake = _frontend_render(
            {
                "retracted": True,
                "gate": "citation-validation",
                "streamed_chars": 214,
                "result": _refusal_result(refusal_gate="citation-validation"),
            }
        )
        said = fake.text_of("text")
        assert "shown a moment ago" in said
        assert "nothing to withdraw" not in said

    def _replay(self, events: list[tuple[str, dict]]) -> dict:
        """Fold a real SSE event order through the shipped reducer."""
        ns = _frontend_namespace()
        entry: dict = {}
        streamed = ""
        for event, payload in events:
            streamed = ns["record_event"](entry, event, payload, streamed)
        return entry

    def test_retract_before_any_token_records_zero(self):
        """The APU order: status heartbeats, then retract, no token ever."""
        entry = self._replay(
            [
                ("status", {"stage": "retrieval"}),
                ("status", {"stage": "generating"}),
                ("retract", {"gate": "llm"}),
                ("result", _refusal_result()),
            ]
        )
        assert entry["streamed_chars"] == 0

    def test_tokens_then_retract_records_what_was_shown(self):
        entry = self._replay(
            [
                ("token", {"text": "The workflow is"}),
                ("token", {"text": " as follows"}),
                ("retract", {"gate": "citation-validation"}),
                ("result", _refusal_result(refusal_gate="citation-validation")),
            ]
        )
        assert entry["streamed_chars"] == len("Theworkflowisasfollows")

    def test_transport_retract_after_tokens_is_not_treated_as_silent(self):
        """The API retracts with gate `transport` when generation dies after
        tokens were already forwarded — text WAS on screen."""
        entry = self._replay(
            [
                ("token", {"text": "Remove the four bolts"}),
                ("retract", {"gate": "transport"}),
                ("error", {"message": "MiniMax chat stream failed mid-stream"}),
            ]
        )
        assert entry["streamed_chars"] > 0
        assert entry["error"]

    def test_invisible_tokens_do_not_count_as_text_on_screen(self):
        entry = self._replay([("token", {"text": "\u200b \n"}), ("retract", {"gate": "llm"})])
        assert entry["streamed_chars"] == 0

    def test_a_turn_that_never_recorded_the_count_says_so(self):
        """An entry stored by an older client: absent is not zero."""
        fake = _frontend_render({"retracted": True, "gate": "llm", "result": _refusal_result()})
        assert "did not record" in fake.text_of("text")

    def test_gate_labels_are_noun_phrases(self):
        """Labels are read after "Gate:" and "Retracted · gate:", so a
        sentence-shaped label renders as broken grammar."""
        for gate, label in _frontend_dict("GATE_LABELS").items():
            assert not label.startswith("model judged"), f"{gate}: {label!r} reads as a clause"

    def test_backend_error_text_never_reaches_a_markdown_renderer(self):
        """An indexing error can quote the uploaded document."""
        hostile = "[Run repair](https://attacker.example)"
        fake = _frontend_render({"error": hostile})
        assert hostile in fake.text_of("text")
        assert hostile not in fake.text_of("error")
