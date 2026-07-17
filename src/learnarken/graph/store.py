"""Neo4j dependency-graph store over the HTTP tx API (Day 5, spec Q1 ruling).

Same architectural stance as `vespa/store.py`: the engine sits behind this
one module (swapping it means rewriting this file and nothing else), accessed
over plain HTTP — no driver dependency. Local-dev credentials are the
documented throwaway pair from docs/local-services.md.

Graph shape (tutorial 06 §9, interface ③ scope):
    (:DM {dmc, title, package})-[:REFS]->(:DM)      # dmRefs
    (:DM)-[:USES_ICN]->(:ICN {ident})               # illustration refs
Sync is MERGE-based and therefore idempotent (INV-2), mirroring the Vespa
feed. Referenced DMs outside the indexed corpus become bare nodes (no title)
— dangling references stay visible rather than being dropped.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request

from pydantic import BaseModel

from learnarken.chunking.base import Chunk

logger = logging.getLogger("learnarken")

BASE_URL = "http://127.0.0.1:7474"  # loopback: Neo4j has no network auth here
_TX_ENDPOINT = "/db/neo4j/tx/commit"


def _credentials() -> tuple[str, str]:
    """Neo4j credentials from the repo-root .env (red-team day5 #7), with the
    documented local-dev pair as the fallback so a fresh checkout still runs."""
    from learnarken.config import REPO_ROOT

    env = REPO_ROOT / ".env"
    user, password = "neo4j", "learnarken"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("NEO4J_USER="):
                user = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("NEO4J_PASSWORD="):
                password = line.split("=", 1)[1].strip().strip('"').strip("'")
    return user, password


class GraphError(RuntimeError):
    """Neo4j is unreachable or rejected the request. Callers must not proceed."""


class GraphFacts(BaseModel):
    """Interface-③ facts for one DM, injected as structured prompt context."""

    dmc: str
    title: str = ""
    outbound_refs: list[str] = []
    inbound_refs: list[str] = []
    icns: list[str] = []


def _request(path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    user, password = _credentials()
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    request = urllib.request.Request(  # noqa: S310 — fixed localhost scheme
        BASE_URL + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {token}"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise GraphError(f"{path} -> HTTP {exc.code}: {exc.read()[:300].decode()}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise GraphError(f"{path} -> {exc}. Is the learnarken-neo4j container running?") from exc


def _cypher(statements: list[tuple[str, dict]]) -> list[dict]:
    """Run parameterized statements in one transaction; fail closed on any error."""
    payload = {
        "statements": [
            {"statement": statement, "parameters": parameters}
            for statement, parameters in statements
        ]
    }
    body = _request(_TX_ENDPOINT, payload)
    if body.get("errors"):
        raise GraphError(f"cypher failed: {body['errors'][:2]}")
    return body.get("results", [])


def is_up() -> bool:
    try:
        _cypher([("RETURN 1", {})])
        return True
    except GraphError:
        return False


def sync(chunks: list[Chunk], owner: dict[str, str]) -> dict[str, int]:
    """Upsert the DM/ICN dependency graph from the chunks being indexed.

    `owner` maps chunk_id → package name (the same mapping fed to Vespa), so
    graph nodes and vector documents agree on package identity.
    """
    dms: dict[str, dict] = {}
    for chunk in chunks:
        dm = dms.setdefault(
            chunk.dmc,
            {
                "dmc": chunk.dmc,
                "title": chunk.dm_title,
                "package": owner[chunk.chunk_id],
                "refs": set(),
                "icns": set(),
            },
        )
        dm["refs"].update(chunk.outbound_dm_refs)
        dm["icns"].update(chunk.icn_refs)

    statements: list[tuple[str, dict]] = [
        (
            "MERGE (d:DM {dmc: $dmc}) SET d.title = $title, d.package = $package",
            {"dmc": dm["dmc"], "title": dm["title"], "package": dm["package"]},
        )
        for dm in dms.values()
    ]
    edges = 0
    for dm in dms.values():
        for ref in sorted(dm["refs"]):
            statements.append(
                (
                    "MERGE (d:DM {dmc: $dmc}) MERGE (t:DM {dmc: $ref}) MERGE (d)-[:REFS]->(t)",
                    {"dmc": dm["dmc"], "ref": ref},
                )
            )
            edges += 1
        for icn in sorted(dm["icns"]):
            statements.append(
                (
                    "MERGE (d:DM {dmc: $dmc}) MERGE (i:ICN {ident: $icn}) "
                    "MERGE (d)-[:USES_ICN]->(i)",
                    {"dmc": dm["dmc"], "icn": icn},
                )
            )
            edges += 1
    _cypher(statements)
    logger.info("graph sync: %d DM nodes, %d edges", len(dms), edges)
    return {"dm_nodes": len(dms), "edges": edges}


def facts(dmcs: list[str]) -> list[GraphFacts]:
    """Interface-③ context: refs in/out and ICNs for each retrieved DM."""
    statements = [
        (
            "MATCH (d:DM {dmc: $dmc}) "
            "OPTIONAL MATCH (d)-[:REFS]->(o:DM) "
            "OPTIONAL MATCH (i:DM)-[:REFS]->(d) "
            "OPTIONAL MATCH (d)-[:USES_ICN]->(icn:ICN) "
            "RETURN d.dmc, d.title, collect(DISTINCT o.dmc), "
            "collect(DISTINCT i.dmc), collect(DISTINCT icn.ident)",
            {"dmc": dmc},
        )
        for dmc in dict.fromkeys(dmcs)  # de-dup, keep order
    ]
    results = _cypher(statements)
    collected: list[GraphFacts] = []
    for result in results:
        for row in result.get("data", []):
            dmc, title, outbound, inbound, icns = row["row"]
            collected.append(
                GraphFacts(
                    dmc=dmc,
                    title=title or "",
                    outbound_refs=sorted(x for x in outbound if x),
                    inbound_refs=sorted(x for x in inbound if x),
                    icns=sorted(x for x in icns if x),
                )
            )
    return collected
