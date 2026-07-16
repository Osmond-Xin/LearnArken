"""Vespa dense-vector store (Day 4a, docs/specs/day4.md).

Vespa's whole job here is `nearestNeighbor` + attribute filtering. BM25, RRF
and reranking live in Python (spec Q3/Q4), so this module is the *only* place
that knows Vespa exists — swapping the engine means rewriting this file and
nothing else.

INV-2: the document id is the Day 3 deterministic `chunk_id`, so feeding is an
upsert and re-feeding is idempotent; sharding stays behind this abstraction and
no caller reaches around it.
"""

from __future__ import annotations

import http.client
import json
import logging
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from learnarken.chunking.base import Chunk
from learnarken.models import Applicability, ApplicAssertion

logger = logging.getLogger("learnarken")

# YQL is assembled by string interpolation, so every interpolated value is
# validated first (red-team day4 #9): strategies against the chunking
# registry, package names against a conservative charset, top_k clamped.
_SAFE_PACKAGE = re.compile(r"^[A-Za-z0-9._-]+$")
MAX_TOP_K = 400

APP_DIR = Path(__file__).parent / "app"
CONFIG_URL = "http://localhost:19071"
QUERY_URL = "http://localhost:8080"
CONTAINER = "learnarken-vespa"
NAMESPACE = "learnarken"
DOC_TYPE = "chunk"


class VespaError(RuntimeError):
    """Vespa is unreachable or rejected the request. Callers must not proceed."""


def _request(url: str, payload: dict | None = None, method: str = "GET", timeout: int = 30) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(  # noqa: S310 — fixed localhost scheme
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise VespaError(f"{method} {url} -> HTTP {exc.code}: {exc.read()[:300].decode()}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as exc:
        # ConnectionError/HTTPException cover RemoteDisconnected: the container
        # port is open before the service answers, which urlopen does not wrap
        # in URLError (seen live during the 2026-07-16 container recreation).
        raise VespaError(f"{method} {url} -> {exc}. Is the {CONTAINER} container running?") from exc


def is_up(url: str = QUERY_URL) -> bool:
    """Is the query container answering? Used to skip integration tests."""
    try:
        _request(f"{url}/state/v1/health", timeout=3)
        return True
    except VespaError:
        return False


def deploy(app_dir: Path = APP_DIR, wait: int = 120) -> None:
    """Deploy the application package via the container's own vespa CLI.

    The package is copied into the container and deployed from there — the
    config server's HTTP deploy API wants a zipped package, and shelling out to
    the CLI that ships in the image is the smaller moving part.
    """
    subprocess.run(  # noqa: S603
        ["docker", "cp", f"{app_dir}/.", f"{CONTAINER}:/tmp/learnarken-app"],
        check=True,
        capture_output=True,
    )
    result = subprocess.run(  # noqa: S603
        [
            "docker",
            "exec",
            CONTAINER,
            "vespa",
            "deploy",
            "--wait",
            str(wait),
            "/tmp/learnarken-app",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise VespaError(f"vespa deploy failed:\n{result.stdout}\n{result.stderr}")
    logger.info("Vespa application deployed")

    deadline = time.time() + wait
    while time.time() < deadline:
        if is_up():
            return
        time.sleep(2)
    raise VespaError(f"deployed, but {QUERY_URL} did not come up within {wait}s")


def _document_fields(chunk: Chunk, package: str) -> dict:
    applic = chunk.applicability
    return {
        "chunk_id": chunk.chunk_id,
        "package": package,
        "dmc": chunk.dmc,
        "dm_title": chunk.dm_title,
        "issue_info": chunk.issue_info,
        "chunk_type": chunk.chunk_type,
        "source_path": chunk.source_path,
        "strategy": chunk.strategy,
        "text": chunk.text,
        "has_warning": chunk.has_warning,
        "has_caution": chunk.has_caution,
        "outbound_dm_refs": chunk.outbound_dm_refs,
        "icn_refs": chunk.icn_refs,
        "applic_display": applic.display_text if applic else "",
        "applic_properties": [a.property_ident for a in applic.assertions] if applic else [],
        "applic_values": [a.values for a in applic.assertions] if applic else [],
        "security_classification": chunk.security_classification or "",
        "effective_date": chunk.effective_date.isoformat() if chunk.effective_date else "",
        "expiry_date": chunk.expiry_date.isoformat() if chunk.expiry_date else "",
    }


def _chunk_from_fields(fields: dict) -> Chunk:
    properties = fields.get("applic_properties") or []
    values = fields.get("applic_values") or []
    applicability = (
        Applicability(
            display_text=fields.get("applic_display") or "",
            assertions=[
                ApplicAssertion(property_ident=p, property_type="", values=v)
                for p, v in zip(properties, values, strict=True)
            ],
        )
        if properties or fields.get("applic_display")
        else None
    )
    return Chunk(
        chunk_id=fields["chunk_id"],
        strategy=fields["strategy"],
        dmc=fields["dmc"],
        dm_title=fields.get("dm_title", ""),
        issue_info=fields.get("issue_info", ""),
        chunk_type=fields["chunk_type"],
        source_path=fields["source_path"],
        text=fields.get("text", ""),
        applicability=applicability,
        security_classification=fields.get("security_classification") or None,
        effective_date=fields.get("effective_date") or None,
        expiry_date=fields.get("expiry_date") or None,
        has_warning=fields.get("has_warning", False),
        has_caution=fields.get("has_caution", False),
        outbound_dm_refs=fields.get("outbound_dm_refs") or [],
        icn_refs=fields.get("icn_refs") or [],
    )


def feed(chunks: list[Chunk], vectors: list[list[float]], packages: list[str]) -> int:
    """Upsert chunks with their embeddings. Idempotent: doc id = chunk_id (INV-2).

    `packages[i]` is the owning package name of `chunks[i]` (directory
    basename) — stored as an attribute so search can scope to one package
    engine-side (red-team day4 #5).
    """
    if not (len(chunks) == len(vectors) == len(packages)):
        raise VespaError(
            f"{len(chunks)} chunks / {len(vectors)} vectors / {len(packages)} package "
            "names — refusing to feed"
        )
    bad = sorted({p for p in packages if not _SAFE_PACKAGE.match(p)})
    if bad:
        raise VespaError(f"invalid package name(s) {bad} — refusing to feed")
    for chunk, vector, package in zip(chunks, vectors, packages, strict=True):
        url = f"{QUERY_URL}/document/v1/{NAMESPACE}/{DOC_TYPE}/docid/{chunk.chunk_id}"
        fields = _document_fields(chunk, package)
        fields["embedding"] = {"values": vector}
        _request(url, {"fields": fields}, method="POST")
    logger.info("fed %d chunks to Vespa", len(chunks))
    return len(chunks)


def clear() -> None:
    """Drop every document of this type. Keeps re-indexing runs honest."""
    _request(
        f"{QUERY_URL}/document/v1/{NAMESPACE}/{DOC_TYPE}/docid?selection=true&cluster=learnarken",
        method="DELETE",
    )


def delete(chunk_id: str) -> None:
    """Delete one document by chunk id (integration-test cleanup)."""
    _request(
        f"{QUERY_URL}/document/v1/{NAMESPACE}/{DOC_TYPE}/docid/{chunk_id}",
        method="DELETE",
    )


def count() -> int:
    body = _request(
        f"{QUERY_URL}/search/?yql=select+*+from+{DOC_TYPE}+where+true&hits=0",
        timeout=15,
    )
    return int(body.get("root", {}).get("fields", {}).get("totalCount", 0))


def list_doc_ids() -> set[str]:
    """Every document id currently in the engine, via the visit API.

    The ground truth for corpus-identity verification (red-team day4 #4):
    unlike `count()`, a set comparison cannot be fooled by a stale or mixed
    index that happens to have the right size.
    """
    ids: set[str] = set()
    continuation = ""
    while True:
        url = f"{QUERY_URL}/document/v1/{NAMESPACE}/{DOC_TYPE}/docid?wantedDocumentCount=1024"
        if continuation:
            url += f"&continuation={continuation}"
        body = _request(url, timeout=30)
        for doc in body.get("documents", []):
            ids.add(doc["id"].rsplit("::", 1)[-1])
        continuation = body.get("continuation", "")
        if not continuation:
            return ids


def search(
    vector: list[float],
    top_k: int = 10,
    strategy: str | None = None,
    package: str | None = None,
    approximate: bool = False,
) -> list[tuple[Chunk, float]]:
    """Nearest-neighbour search. Returns (chunk, relevance) ranked best first.

    `package` scopes the search to one package engine-side and fails closed if
    the engine still returns an out-of-scope chunk (red-team day4 #5 — a Day 5
    answer must never cite another package). `approximate=False` by default:
    at this corpus size HNSW and brute force give the same answers, and exact
    search keeps the ablation free of an ANN-approximation confound (spec,
    Interfaces). Flip it to True to demonstrate the HNSW-vs-exact trade-off.
    """
    from learnarken.chunking import STRATEGIES

    if strategy is not None and strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; choose from {sorted(STRATEGIES)}")
    if package is not None and not _SAFE_PACKAGE.match(package):
        raise ValueError(f"invalid package name {package!r}")
    if not isinstance(approximate, bool):  # str would be interpolated into YQL (C5)
        raise ValueError(f"approximate must be a bool, got {type(approximate).__name__}")
    top_k = max(1, min(int(top_k), MAX_TOP_K))
    nn = f"{{targetHits:{top_k}, approximate:{str(approximate).lower()}}}"
    conditions = [f"({nn}nearestNeighbor(embedding, q))"]
    if strategy:
        conditions.append(f'strategy contains "{strategy}"')
    if package:
        conditions.append(f'package contains "{package}"')
    payload = {
        "yql": f"select * from {DOC_TYPE} where {' and '.join(conditions)}",
        "ranking.profile": "dense",
        "input.query(q)": {"values": vector},
        "hits": top_k,
    }
    body = _request(f"{QUERY_URL}/search/", payload, method="POST")
    hits = body.get("root", {}).get("children", []) or []
    results: list[tuple[Chunk, float]] = []
    for h in hits:
        fields = h["fields"]
        if package and fields.get("package") != package:
            raise VespaError(
                f"engine returned chunk {fields.get('chunk_id')!r} from package "
                f"{fields.get('package')!r} outside requested scope {package!r} (fail closed)"
            )
        results.append((_chunk_from_fields(fields), float(h.get("relevance", 0.0))))
    return results
