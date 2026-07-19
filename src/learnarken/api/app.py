"""Day 6 FastAPI backend (docs/specs/day6.md): upload + SSE Q&A demo.

Design constraints, in order of importance:

- **Fail closed everywhere** (INV-4): a rejected upload leaves the active
  corpus exactly as it was; a query-time service failure becomes an `error`
  event, never a degraded answer.
- **Uploads are transactional on disk** (red-team day6 #1): the candidate is
  validated and indexed inside a *staging* copy of the uploads package; the
  active directory is only ever swapped — atomically — to a set of files that
  already passed validation AND indexing. A rejected or failed upload never
  destroys the previously-valid module, and the active dir never holds an
  unvalidated file. (Engine-internal partial-index consistency — a Vespa feed
  that half-succeeds — is the separate day5 #8 index-epoch item; a query then
  fails closed on `verify_corpus`.)
- **Routes are sync `def` on purpose**: the whole answer stack (urllib LLM
  client, sentence-transformers, reranker) is synchronous — `async def`
  routes would block the event loop. Starlette runs `def` routes in its
  threadpool; the SSE generator drains a queue fed by a worker thread.
- **SSE with retraction** (decision 3): `token` events are pre-verification
  by design; a `retract` event orders the client to withdraw them — emitted
  both when a fail-closed gate voids a generation AND when the stream aborts
  mid-flight after tokens were shown (red-team day6 #3). The `result` (or
  `error`) event is the only authoritative outcome.
- **Demo security envelope** (decision 4): loopback bind (the `make demo`
  script); a same-origin guard on state-changing routes rejects browser
  cross-origin CSRF (red-team day6 #4); Pydantic length bounds on the
  question; uploads are size- (pre- and post-parse), name-, and UTF-8-checked
  before the four-layer validator runs; filenames are re-derived server-side.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from learnarken import graph, vespa
from learnarken.answer import answer_question
from learnarken.answer.engine import DEFAULT_PACKAGES, load_threshold
from learnarken.api.demo_guard import GUARD
from learnarken.config import REPO_ROOT, load_minimax_config
from learnarken.package import NotAPackageError, _sanitize
from learnarken.retrieval import index_package
from learnarken.validation import analyze_package

logger = logging.getLogger("learnarken")

UPLOAD_PACKAGE = REPO_ROOT / "var" / "uploads" / "package-upload"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
_MULTIPART_SLACK = 8 * 1024  # multipart boundary/header overhead over the raw file
# Server-side re-derived basename: no separators, no dotfiles, .xml only.
# The DMC- prefix is load-bearing: the package scanner only recognizes
# DMC-/PMC-/DML-*.xml, so any other name would be silently ignored by
# validation and chunking — an unvalidated file claiming "ingested"
# (found live 2026-07-17: broken.xml sailed through as a no-op).
_SAFE_NAME = re.compile(r"DMC-[A-Za-z0-9][A-Za-z0-9._-]{0,195}\.xml", re.IGNORECASE)
# CSRF defense (demo scope): a browser sends `Origin`/`Referer` on cross-origin
# POSTs; server-side clients (Streamlit's `requests`, curl) send neither. Any
# present origin must be loopback, else refuse (red-team day6 #4).
_ALLOWED_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "::1"}
# Exception type names treated as fail-closed service errors — mirrors the CLI's
# INV-4 mapping (cli.py) intentionally: a service/validation failure is reported
# with a sanitized message, never a degraded answer. Every match is also logged
# so a mis-classified programmer error is still visible (red-team day6 #8).
_FAIL_CLOSED = (
    "VespaError",
    "GraphError",
    "LLMError",
    "ConfigError",
    "EmbeddingError",
    "ValueError",
    "PartialPackageError",
    "NotAPackageError",
    "DemoQuotaExceeded",  # public-demo spend/concurrency fence (day10 #2)
)

# On-demand demo bookkeeping (SPEC day10): the idle watchdog and the public
# status page read these through /demo/status. Only *business* endpoints
# (/query, /upload) touch the activity clock — health/status polling must
# never reset it, or the 30-minute idle shutdown would never fire (unknowns
# T1). Plain float writes are atomic enough under the GIL for this purpose.
_STARTED_AT = time.time()
_activity: dict[str, float | None] = {"ts": None}


def _touch_activity() -> None:
    _activity["ts"] = time.time()


# Serializes upload commits against each other AND against the brief active-dir
# swap. Queries are not held here (they re-chunk from disk, and staging
# guarantees the active dir only ever holds committed files); a query racing
# the sub-millisecond swap can at worst fail closed, never read uncommitted
# content (red-team day6 #5).
_corpus_lock = threading.Lock()


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def _jsonable(obj: object) -> object:
    """Round-trip through json to stringify dates etc. (CLI uses default=str)."""
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _guard_csrf(request: Request) -> None:
    """Refuse a browser cross-origin state-changing request (day6 #4)."""
    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin:
        return  # server-side client (no Origin/Referer): allowed
    host = urlparse(origin).hostname
    if host not in _ALLOWED_ORIGIN_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="cross-origin request refused (the demo is loopback-only)",
        )


def _guard_demo_key(request: Request) -> None:
    """Public-mode shared-key gate on spending/mutating routes (day10 #1).

    No-op outside `DEMO_PUBLIC=1`, so local `make demo` and tests are
    unchanged. The visitor's Streamlit client forwards the key it received
    from the token status page as `X-Demo-Key`.
    """
    if not GUARD.key_ok(request.headers.get("x-demo-key")):
        raise HTTPException(status_code=403, detail="demo access key required or invalid")


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _query_packages() -> list[str]:
    """Base corpus plus the uploads package once it holds any module."""
    packages = [str(p) for p in DEFAULT_PACKAGES]
    if UPLOAD_PACKAGE.is_dir() and any(
        p.suffix.lower() == ".xml" for p in UPLOAD_PACKAGE.iterdir()
    ):
        packages.append(str(UPLOAD_PACKAGE))
    return packages


def _recover_interrupted_swap() -> None:
    """Restore the active dir if a swap crashed between its two renames."""
    trash = UPLOAD_PACKAGE.parent / (UPLOAD_PACKAGE.name + ".trash")
    if trash.is_dir() and not UPLOAD_PACKAGE.exists():
        os.replace(trash, UPLOAD_PACKAGE)
    else:
        _rmtree(trash)


def _swap_into_active(staging: Path) -> None:
    """Atomically make `staging` the active uploads dir. Each `os.replace` is
    atomic; the gap between them (active absent) is covered by `_corpus_lock`,
    and a crash inside it is repaired by `_recover_interrupted_swap` at start."""
    active = UPLOAD_PACKAGE
    trash = active.parent / (active.name + ".trash")
    _rmtree(trash)
    active.parent.mkdir(parents=True, exist_ok=True)
    if active.exists():
        os.replace(active, trash)
    os.replace(staging, active)
    _rmtree(trash)


def _staged_commit(name: str, data: bytes) -> tuple[int, dict]:
    """Validate + index the prospective corpus in staging; swap in on success.

    The active uploads dir is never mutated until both validation and indexing
    pass, so a rejection or index failure preserves the previously-valid state
    (red-team day6 #1).
    """
    staging_parent = UPLOAD_PACKAGE.parent / ".staging"
    # Same basename as the active dir: the basename is the engine-side package
    # scope identity, so staging must not shift it (retrieval/__init__.py).
    staging = staging_parent / UPLOAD_PACKAGE.name

    with _corpus_lock:
        try:
            _rmtree(staging_parent)
            staging.mkdir(parents=True)
            if UPLOAD_PACKAGE.is_dir():
                for existing in UPLOAD_PACKAGE.glob("*.xml"):
                    shutil.copy2(existing, staging / existing.name)
            replaced = (staging / name).exists()
            (staging / name).write_bytes(data)

            try:
                report, package = analyze_package(str(staging))
            except NotAPackageError as exc:
                return 422, {"status": "rejected", "filename": name, "message": _sanitize(str(exc))}
            if name not in {dm.file for dm in package.data_modules}:
                # Validation "passed" without ever parsing this file — a file the
                # scanner does not cover must never count as ingested.
                return 422, {
                    "status": "rejected",
                    "filename": name,
                    "message": "file was not recognized as a data module by the "
                    "package scanner (fail closed)",
                }
            if report.error_count:
                return 422, {
                    "status": "rejected",
                    "filename": name,
                    "report": _jsonable(report.to_dict()),
                }

            try:
                indexed = index_package([*DEFAULT_PACKAGES, str(staging)], strategy="structure")
            except Exception as exc:
                if type(exc).__name__ not in _FAIL_CLOSED:
                    raise
                logger.warning("upload index failed (fail closed): %s", exc, exc_info=exc)
                return 503, {
                    "status": "index_failed",
                    "filename": name,
                    "message": _sanitize(f"{type(exc).__name__}: {exc}"),
                }

            _swap_into_active(staging)
        finally:
            # Always clear staging — on every return path, on an unexpected
            # validator/index exception, and after a successful swap (which
            # leaves only the empty parent). The active dir is never touched
            # except by the swap above, so cleanup cannot corrupt it.
            _rmtree(staging_parent)

    return 200, {
        "status": "ingested",
        "filename": name,
        "replaced": replaced,
        "indexed_chunks": indexed,
        "report": _jsonable(report.to_dict()),
    }


def _probe(check) -> dict:
    """Run one health check: falsy return or any exception ⇒ not ok."""
    try:
        result = check()
        if result is not None and not result:
            return {"ok": False, "detail": "unreachable"}
        return {"ok": True}
    except Exception as exc:  # a health probe reports, never raises
        return {"ok": False, "detail": _sanitize(f"{type(exc).__name__}: {exc}")[:200]}


def create_app() -> FastAPI:
    if Path.cwd().resolve() != REPO_ROOT:
        # Trace dir and .vespa-manifest.json are cwd-relative (backlog #10);
        # refuse to start from anywhere else rather than scatter artifacts.
        raise RuntimeError(
            f"the API must run from the repo root {REPO_ROOT} "
            f"(cwd is {Path.cwd()}) — use `make demo`"
        )
    _recover_interrupted_swap()
    app = FastAPI(title="LearnArken demo API", version="0.6.0")

    @app.get("/health")
    def health() -> dict:
        services = {
            "vespa": _probe(vespa.is_up),
            "neo4j": _probe(graph.is_up),
            "minimax_config": _probe(load_minimax_config),
            "threshold_artifact": _probe(load_threshold),
        }
        ok = all(s["ok"] for s in services.values())
        return {"status": "ok" if ok else "degraded", "services": services}

    @app.get("/demo/status")
    def demo_status() -> dict:
        """Public self-check for the on-demand demo (SPEC day10).

        Deliberately coarser than /health: stage booleans only, never probe
        detail strings — details can carry exception text and this endpoint is
        exposed beyond loopback via the VM status shim (unknowns T2).
        """
        services = {
            "vespa": _probe(vespa.is_up)["ok"],
            "neo4j": _probe(graph.is_up)["ok"],
            "llm_config": _probe(load_minimax_config)["ok"],
            "threshold_artifact": _probe(load_threshold)["ok"],
        }
        now = time.time()
        last = _activity["ts"]
        return {
            "status": "ready" if all(services.values()) else "degraded",
            "services": services,
            "started_at": _STARTED_AT,
            "uptime_seconds": round(now - _STARTED_AT, 1),
            "last_business_activity": last,
            "idle_seconds": round(now - (last if last is not None else _STARTED_AT), 1),
        }

    @app.post("/upload")
    def upload(request: Request, file: UploadFile):
        _guard_csrf(request)
        if not GUARD.uploads_allowed():
            # Uploads mutate the shared live corpus and persist across visitors
            # (day10 #4) — refused outright on the public demo.
            raise HTTPException(status_code=403, detail="uploads are disabled on the public demo")
        _guard_demo_key(request)
        _touch_activity()
        content_length = request.headers.get("content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > MAX_UPLOAD_BYTES + _MULTIPART_SLACK
        ):
            # Reject before python-multipart spools the whole body to disk.
            raise HTTPException(status_code=413, detail="upload exceeds the 2 MiB limit")
        name = Path(file.filename or "").name
        if not _SAFE_NAME.fullmatch(name):
            raise HTTPException(
                status_code=400,
                detail="filename must be a plain DMC-*.xml basename of [A-Za-z0-9._-] "
                "(only data modules can be uploaded)",
            )
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="file exceeds the 2 MiB upload limit")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="file is not valid UTF-8") from exc

        status_code, payload = _staged_commit(name, data)
        if status_code == 200:
            return payload
        return JSONResponse(status_code=status_code, content=payload)

    @app.post("/query")
    def query(request: Request, body: QueryRequest) -> StreamingResponse:
        _guard_csrf(request)
        _guard_demo_key(request)
        _touch_activity()

        def events():
            beats: queue.Queue = queue.Queue()
            outcome: dict = {}

            def on_event(kind: str, data: dict) -> None:
                beats.put((kind, data))

            def work() -> None:
                # The spend fence is entered *inside* the worker so an over-quota
                # request still streams a clean fail-closed error (day10 #2). The
                # slot is held for the whole generation, bounding concurrency.
                try:
                    with GUARD.llm_slot():
                        outcome["result"] = answer_question(
                            body.question,
                            package_dirs=_query_packages(),
                            on_event=on_event,
                        )
                except Exception as exc:  # reported below, fail closed
                    outcome["error"] = exc
                finally:
                    beats.put(None)

            worker = threading.Thread(target=work, daemon=True)
            worker.start()
            tokens_emitted = False
            while (item := beats.get()) is not None:
                kind, data = item
                if kind == "token":
                    tokens_emitted = True
                yield _sse(kind, data)
            if "error" in outcome:
                exc = outcome["error"]
                if tokens_emitted:
                    # The stream aborted after showing unverified tokens — the
                    # retraction contract must hold for transport failures too,
                    # not only gate refusals (red-team day6 #3).
                    yield _sse(
                        "retract",
                        {
                            "gate": "transport",
                            "message": "generation was interrupted; the streamed "
                            "content is unverified and has been retracted",
                        },
                    )
                if type(exc).__name__ in _FAIL_CLOSED:
                    logger.warning("query failed (fail closed): %s", exc, exc_info=exc)
                    message = _sanitize(f"{type(exc).__name__}: {exc}")
                else:
                    logger.error("unexpected /query failure", exc_info=exc)
                    message = "internal error (fail closed)"
                yield _sse("error", {"message": message})
            else:
                yield _sse("result", _jsonable(outcome["result"].model_dump()))
            yield _sse("done", {})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
