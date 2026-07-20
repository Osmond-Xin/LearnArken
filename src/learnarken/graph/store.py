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


class ImpactedDM(BaseModel):
    """A DM that (transitively) depends on the queried DM, with its hop distance."""

    dmc: str
    title: str = ""
    hops: int


class ImpactResult(BaseModel):
    """Reverse-dependency impact for one DM (Day 9, ADR-0002 interface ①).

    `affected` lists the DMs that would be hit if `target` were superseded,
    ordered by hop distance. Existence is split (red-team day9 #6): `sync()`
    creates bare nodes for dangling refs, so a DMC can appear as a graph node
    (`exists_as_reference`) without being an indexed corpus module
    (`exists_in_corpus`, i.e. carrying a package). `truncated` is True when the
    result cap was hit before the traversal finished.
    """

    target: str
    exists_in_corpus: bool
    exists_as_reference: bool
    depth: int
    truncated: bool = False
    affected: list[ImpactedDM] = []


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
            raw = response.read() or b"{}"
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace")
        raise GraphError(f"{path} -> HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise GraphError(f"{path} -> {exc}. Is the learnarken-neo4j container running?") from exc
    # A non-JSON / non-object body means something other than Neo4j answered on
    # 127.0.0.1:7474 — fail closed rather than let a decode error escape (day9 #3).
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GraphError(f"{path} -> non-JSON response ({len(raw)} bytes); is this Neo4j?") from exc
    if not isinstance(body, dict):
        raise GraphError(f"{path} -> unexpected JSON type {type(body).__name__}, expected object")
    return body


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
    results = body.get("results")
    # One result block per statement; a mismatch means a wrong/degraded endpoint
    # (e.g. HTTP 200 `{}`) — fail closed instead of returning silent empties (day9 #3).
    if not isinstance(results, list) or len(results) != len(statements):
        got = len(results) if isinstance(results, list) else type(results).__name__
        raise GraphError(f"cypher: expected {len(statements)} result blocks, got {got}")
    return results


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
    # MERGE alone is append-only: edges/nodes from a previous, different corpus
    # would survive and silently feed the Day 11 retrieval route (red-team
    # day11 #1). Make the sync corpus-authoritative in the same transaction:
    # drop edges the current chunks no longer assert, orphan nodes nobody
    # references, and the `package` mark on DMs that are no longer indexed.
    indexed = sorted(dms)
    known_dms = sorted(set(dms) | {r for dm in dms.values() for r in dm["refs"]})
    known_icns = sorted({i for dm in dms.values() for i in dm["icns"]})
    for dm in dms.values():
        statements.append(
            (
                "MATCH (d:DM {dmc: $dmc})-[r:REFS]->(t:DM) WHERE NOT t.dmc IN $refs DELETE r",
                {"dmc": dm["dmc"], "refs": sorted(dm["refs"])},
            )
        )
        statements.append(
            (
                "MATCH (d:DM {dmc: $dmc})-[r:USES_ICN]->(i:ICN) "
                "WHERE NOT i.ident IN $icns DELETE r",
                {"dmc": dm["dmc"], "icns": sorted(dm["icns"])},
            )
        )
    statements.append(
        ("MATCH (d:DM) WHERE NOT d.dmc IN $known DETACH DELETE d", {"known": known_dms})
    )
    statements.append(
        ("MATCH (i:ICN) WHERE NOT i.ident IN $known DETACH DELETE i", {"known": known_icns})
    )
    statements.append(
        # A previously-indexed DM that is now only referenced must stop
        # claiming corpus membership (exists_in_corpus semantics, day9 #6).
        ("MATCH (d:DM) WHERE NOT d.dmc IN $indexed REMOVE d.package", {"indexed": indexed})
    )
    _cypher(statements)
    logger.info("graph sync: %d DM nodes, %d edges", len(dms), edges)
    return {"dm_nodes": len(dms), "edges": edges}


def stats() -> dict[str, int]:
    """Live counts in the same shape `sync` returns, for manifest verification.

    `dm_nodes` counts only indexed modules (carrying a package); `edges` is
    REFS + USES_ICN. After a corpus-authoritative `sync` these must equal the
    manifest's recorded `graph` block — a mismatch means the graph did not
    come from the manifest's ingest (red-team day11 #1, fail closed).
    """
    rows = _cypher(
        [
            ("MATCH (d:DM) WHERE d.package IS NOT NULL RETURN count(d)", {}),
            ("MATCH ()-[r:REFS]->() RETURN count(r)", {}),
            ("MATCH ()-[r:USES_ICN]->() RETURN count(r)", {}),
        ]
    )
    try:
        dm_nodes = rows[0]["data"][0]["row"][0]
        refs = rows[1]["data"][0]["row"][0]
        icns = rows[2]["data"][0]["row"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise GraphError(f"stats: unexpected response shape ({exc!r})") from exc
    return {"dm_nodes": dm_nodes, "edges": refs + icns}


MAX_IMPACT_DEPTH = 10
MAX_IMPACT_RESULTS = 1000  # backstop against pathological fan-out (INV-2 bound)


def impact(dmc: str, depth: int = 3) -> ImpactResult:
    """Which DMs depend on `dmc` — the procedures affected if it were superseded.

    Reverse `dmRef` traversal (interface ①, ADR-0002): a **breadth-first walk**
    against the `REFS` edge direction, one single-hop query per level. Each level
    excludes already-visited nodes, so the walk is cycle-safe by construction
    (package-b's VIO-7 loops cannot re-expand) and — unlike a variable-length
    `REFS*` pattern — never enumerates whole paths, so a dense/cyclic graph cannot
    explode into a DoS (day9 red-team #1). Depth and a result cap
    (`MAX_IMPACT_RESULTS`) bound the work; `truncated` flags the cap. Fails closed
    (`GraphError`) when Neo4j is unreachable (INV-4).

    Existence is split (day9 #6): `exists_as_reference` = the DMC is any graph
    node; `exists_in_corpus` = it is an indexed module (carries a package), not a
    bare dangling-reference placeholder.
    """
    if type(depth) is not int or not (1 <= depth <= MAX_IMPACT_DEPTH):
        raise ValueError(f"depth must be an int in 1..{MAX_IMPACT_DEPTH}, got {depth!r}")

    meta = _cypher(
        [("MATCH (x:DM {dmc: $dmc}) RETURN count(x), head(collect(x.package))", {"dmc": dmc})]
    )
    meta_rows = meta[0].get("data", [])
    node_count, package = meta_rows[0]["row"] if meta_rows else (0, None)
    exists_as_reference = bool(node_count)
    exists_in_corpus = package is not None

    visited = {dmc}
    frontier = [dmc]
    affected: list[ImpactedDM] = []
    truncated = False
    for hop in range(1, depth + 1):
        if not frontier:
            break
        rows = _cypher(
            [
                (
                    "MATCH (a:DM)-[:REFS]->(t:DM) "
                    "WHERE t.dmc IN $frontier AND NOT a.dmc IN $visited "
                    "RETURN DISTINCT a.dmc AS dmc, a.title AS title ORDER BY dmc",
                    {"frontier": frontier, "visited": sorted(visited)},
                )
            ]
        )
        next_frontier: list[str] = []
        for row in rows[0].get("data", []):
            admc, title = row["row"][0], row["row"][1]
            if admc in visited:  # reachable from two frontier nodes in the same hop
                continue
            visited.add(admc)
            affected.append(ImpactedDM(dmc=admc, title=title or "", hops=hop))
            next_frontier.append(admc)
            if len(affected) >= MAX_IMPACT_RESULTS:
                truncated = True
                break
        if truncated:
            break
        frontier = next_frontier

    logger.info(
        "graph impact: target=%s depth=%d affected=%d truncated=%s",
        dmc,
        depth,
        len(affected),
        truncated,
    )
    return ImpactResult(
        target=dmc,
        exists_in_corpus=exists_in_corpus,
        exists_as_reference=exists_as_reference,
        depth=depth,
        truncated=truncated,
        affected=affected,
    )


MAX_EXPAND_DEPTH = 2  # spec Key Decision 2: 1-2 hops, nothing deeper
GRAPH_FANOUT_CAP = 20  # hub guard: per-node neighbor cap, deterministic (ORDER BY dmc)
MAX_EXPAND_NODES = 100  # overall bound on one expansion (INV-2)
MAX_EXPAND_SEEDS = 25  # bound on the seed list itself (red-team day11 #2)


class NeighborDM(BaseModel):
    """A DM discovered by `neighborhood`, with how it was reached."""

    dmc: str
    hops: int  # 1..depth (seeds themselves are not emitted)
    direction: str  # "out" = frontier-[:REFS]->node, "in" = node-[:REFS]->frontier


def neighborhood(seeds: list[str], depth: int = MAX_EXPAND_DEPTH) -> tuple[list[NeighborDM], bool]:
    """DMs within `depth` REFS-hops of `seeds`, both directions, deterministic.

    Same per-hop BFS shape as `impact` (cycle-safe by construction, never
    enumerates paths). Ordering is fully deterministic (INV-5): per hop,
    out-edges before in-edges (edge-direction priority, spec T1), then by
    (frontier dmc, neighbor dmc). The hub guard is a per-node fan-out cap of
    `GRAPH_FANOUT_CAP` neighbors, cut on the same deterministic order — a
    runtime equivalent of the spec's static `is_hub` marking with the same
    bound and less machinery (divergence noted in the day's notes). Fails
    closed (`GraphError`) when Neo4j is unreachable; the *caller* decides
    whether that degrades (search path) or aborts (ablation).
    """
    if type(depth) is not int or not (1 <= depth <= MAX_EXPAND_DEPTH):
        raise ValueError(f"depth must be an int in 1..{MAX_EXPAND_DEPTH}, got {depth!r}")
    if len(set(seeds)) > MAX_EXPAND_SEEDS:
        # The node cap bounds discovery, not the seed lists shipped to Neo4j —
        # an over-broad entity link must be cut by the caller, deterministically,
        # before it reaches the wire (red-team day11 #2).
        raise ValueError(f"{len(set(seeds))} seeds exceed MAX_EXPAND_SEEDS={MAX_EXPAND_SEEDS}")
    visited = set(seeds)
    frontier = sorted(visited)
    found: list[NeighborDM] = []
    truncated = False
    for hop in range(1, depth + 1):
        if not frontier or truncated:
            break
        next_frontier: list[str] = []
        for pattern, direction in (
            ("(s:DM)-[:REFS]->(n:DM)", "out"),
            ("(n:DM)-[:REFS]->(s:DM)", "in"),
        ):
            rows = _cypher(
                [
                    (
                        f"MATCH {pattern} "
                        "WHERE s.dmc IN $frontier AND NOT n.dmc IN $visited "
                        "WITH s, n ORDER BY n.dmc "
                        "WITH s, collect(DISTINCT n.dmc)[0..$fanout] AS ns "
                        "RETURN s.dmc, ns ORDER BY s.dmc",
                        {
                            "frontier": frontier,
                            "visited": sorted(visited),
                            "fanout": GRAPH_FANOUT_CAP,
                        },
                    )
                ]
            )
            try:
                parsed = [(row["row"][0], list(row["row"][1])) for row in rows[0].get("data", [])]
            except (KeyError, IndexError, TypeError) as exc:
                # A proxy / wrong service answering with unexpected JSON must
                # surface as GraphError (degradable), not KeyError (day11 #7).
                raise GraphError(f"neighborhood: unexpected response shape ({exc!r})") from exc
            for _, neighbor_dmcs in parsed:
                for ndmc in neighbor_dmcs:
                    if ndmc in visited:  # reached via an earlier frontier node/direction
                        continue
                    visited.add(ndmc)
                    found.append(NeighborDM(dmc=ndmc, hops=hop, direction=direction))
                    next_frontier.append(ndmc)
                    if len(found) >= MAX_EXPAND_NODES:
                        truncated = True
                        break
                if truncated:
                    break
            if truncated:
                break
        frontier = next_frontier
    logger.info(
        "graph neighborhood: seeds=%d depth=%d found=%d truncated=%s",
        len(seeds),
        depth,
        len(found),
        truncated,
    )
    return found, truncated


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
