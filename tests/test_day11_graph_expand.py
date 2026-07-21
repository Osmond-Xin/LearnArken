"""Day 11 graph expansion: hermetic BFS + retriever tests (spec §2).

Same fake-transport pattern as test_day9_evidence.py: the real traversal logic
runs over a monkeypatched `_cypher`, so cycle-safety, ordering, caps and
degradation are covered without a live Neo4j.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from learnarken.chunking import chunk_package
from learnarken.graph import store
from learnarken.retrieval.graph_expand import graph_expansion_retriever

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_A = REPO_ROOT / "samples" / "package-a"

# (referrer, target) == (a)-[:REFS]->(b). Contains a VIO-7-style cycle A<->B.
_EDGES = {("A", "X"), ("B", "A"), ("C", "B"), ("A", "B"), ("X", "Y")}


def _fake_cypher_for(edges):
    def fake(statements):
        stmt, params = statements[0]
        frontier = set(params["frontier"])
        visited = set(params["visited"])
        fanout = params["fanout"]
        outward = "(s:DM)-[:REFS]->(n:DM)" in stmt
        rows = []
        for source in sorted(frontier):
            if outward:
                neighbors = sorted(b for (a, b) in edges if a == source and b not in visited)
            else:
                neighbors = sorted(a for (a, b) in edges if b == source and a not in visited)
            if neighbors:
                rows.append({"row": [source, neighbors[:fanout]]})
        return [{"data": rows}]

    return fake


def test_neighborhood_both_directions_hops_and_order(monkeypatch) -> None:
    monkeypatch.setattr(store, "_cypher", _fake_cypher_for(_EDGES))
    found, truncated = store.neighborhood(["X"], depth=2)
    by_dmc = {n.dmc: (n.hops, n.direction) for n in found}
    # hop 1: X-[:REFS]->Y (out) and A-[:REFS]->X (in); hop 2: B via A.
    assert by_dmc == {"Y": (1, "out"), "A": (1, "in"), "B": (2, "out")}
    # Deterministic order: out before in within a hop, then discovery order.
    assert [n.dmc for n in found] == ["Y", "A", "B"]
    assert truncated is False


def test_neighborhood_cycle_safe_and_no_seed_reemission(monkeypatch) -> None:
    monkeypatch.setattr(store, "_cypher", _fake_cypher_for(_EDGES))
    found, _ = store.neighborhood(["A", "B"], depth=2)
    dmcs = [n.dmc for n in found]
    assert "A" not in dmcs and "B" not in dmcs  # seeds never re-emitted (cycle A<->B)
    assert len(dmcs) == len(set(dmcs))  # no duplicates despite two seeds


def test_neighborhood_depth_bound(monkeypatch) -> None:
    monkeypatch.setattr(store, "_cypher", _fake_cypher_for(_EDGES))
    found, _ = store.neighborhood(["C"], depth=1)
    assert {n.dmc for n in found} == {"B"}  # A is 2 hops away — not reached


@pytest.mark.parametrize("bad_depth", [0, store.MAX_EXPAND_DEPTH + 1, 2.0, "2"])
def test_neighborhood_depth_validated(bad_depth) -> None:
    with pytest.raises(ValueError, match="depth must be"):
        store.neighborhood(["A"], depth=bad_depth)


def test_neighborhood_hub_fanout_cap_is_deterministic(monkeypatch) -> None:
    """A hub with more neighbors than the cap yields the first cap-many in
    dmc order — a bounded, reproducible cut (spec T2)."""
    hub_edges = {("HUB", f"N{i:03d}") for i in range(store.GRAPH_FANOUT_CAP + 5)}
    monkeypatch.setattr(store, "_cypher", _fake_cypher_for(hub_edges))
    found, _ = store.neighborhood(["N000"], depth=2)
    # hop 1: HUB (in); hop 2: HUB's out-neighbors, capped, in sorted order.
    hop2 = [n.dmc for n in found if n.hops == 2]
    assert len(hop2) == store.GRAPH_FANOUT_CAP
    assert hop2 == sorted(hop2)


def test_neighborhood_total_node_cap(monkeypatch) -> None:
    wide = {("HUB", f"N{i:04d}") for i in range(store.MAX_EXPAND_NODES + 50)}
    monkeypatch.setattr(store, "GRAPH_FANOUT_CAP", store.MAX_EXPAND_NODES + 50)
    monkeypatch.setattr(store, "_cypher", _fake_cypher_for(wide))
    found, truncated = store.neighborhood(["HUB"], depth=1)
    assert truncated is True
    assert len(found) == store.MAX_EXPAND_NODES


# --- The retriever over real package-a chunks ------------------------------

_REAL_EDGES = {
    ("DMC-LA100-A-29-10-00-00A-421A-A", "DMC-LA100-A-29-10-00-00A-520A-A"),
    ("DMC-LA100-A-29-10-00-00A-421A-A", "DMC-LA100-A-29-10-00-00A-720A-A"),
    ("DMC-LA100-A-29-10-00-00A-520A-A", "DMC-LA100-A-29-10-00-00A-941A-D"),
    ("DMC-LA100-A-29-10-00-00A-720A-A", "DMC-LA100-A-29-10-00-00A-520A-A"),
    ("DMC-LA100-A-29-10-00-00A-720A-A", "DMC-LA100-A-29-10-00-00A-941A-D"),
}


@pytest.fixture(scope="module")
def package_a_chunks():
    return chunk_package(PACKAGE_A)


def test_retriever_expands_linked_entity(monkeypatch, package_a_chunks) -> None:
    monkeypatch.setattr(store, "_cypher", _fake_cypher_for(_REAL_EDGES))
    retriever = graph_expansion_retriever(package_a_chunks, k=50)
    documents = retriever.invoke("what part number for LA-29-4711-1 replacement")
    dmcs = {d.metadata["dmc"] for d in documents}
    # Seed: the IPD module owning the part; expansion pulls its REFS neighborhood.
    assert "DMC-LA100-A-29-10-00-00A-941A-D" in dmcs
    assert "DMC-LA100-A-29-10-00-00A-520A-A" in dmcs  # 1 hop (in-edge)
    hop0 = [d for d in documents if d.metadata["graph_hop"] == 0]
    assert hop0 and all(d.metadata["dmc"].endswith("941A-D") for d in hop0)
    assert all("graph_direction" in d.metadata for d in documents)


def test_retriever_is_deterministic(monkeypatch, package_a_chunks) -> None:
    """Spec acceptance 2: same query ⇒ byte-identical ranked list (INV-5)."""
    monkeypatch.setattr(store, "_cypher", _fake_cypher_for(_REAL_EDGES))
    retriever = graph_expansion_retriever(package_a_chunks, k=50)
    query = "hydraulic pump install torque"
    first = [(d.metadata["chunk_id"], d.metadata["graph_hop"]) for d in retriever.invoke(query)]
    second = [(d.metadata["chunk_id"], d.metadata["graph_hop"]) for d in retriever.invoke(query)]
    assert first == second and first


def test_retriever_respects_k(monkeypatch, package_a_chunks) -> None:
    monkeypatch.setattr(store, "_cypher", _fake_cypher_for(_REAL_EDGES))
    retriever = graph_expansion_retriever(package_a_chunks, k=3)
    assert len(retriever.invoke("hydraulic pump")) == 3


def test_retriever_no_entities_never_touches_graph(monkeypatch, package_a_chunks) -> None:
    def explode(statements):  # pragma: no cover - failure path
        raise AssertionError("graph must not be queried when nothing linked")

    monkeypatch.setattr(store, "_cypher", explode)
    retriever = graph_expansion_retriever(package_a_chunks, k=10)
    assert retriever.invoke("completely unrelated question about cooking") == []


def test_retriever_degrades_to_empty_when_neo4j_down(monkeypatch, package_a_chunks) -> None:
    """Search-path semantics: GraphError ⇒ no graph signal, logged — the other
    two routes carry on. Ablation refuses up front instead (run_ablation)."""

    def down(statements):
        raise store.GraphError("connection refused")

    monkeypatch.setattr(store, "_cypher", down)
    retriever = graph_expansion_retriever(package_a_chunks, k=10)
    assert retriever.invoke("hydraulic pump") == []


def test_ablation_refuses_graph_mode_when_neo4j_down(monkeypatch) -> None:
    """Spec: an ablation row must never silently score hybrid+graph as hybrid."""
    from learnarken import retrieval

    monkeypatch.setattr(store, "_cypher", lambda s: (_ for _ in ()).throw(store.GraphError("down")))
    monkeypatch.setattr(retrieval, "verify_corpus", lambda chunks, strategy: None)
    with pytest.raises(ValueError, match="Neo4j is unreachable"):
        retrieval.run_ablation(
            [PACKAGE_A, REPO_ROOT / "samples" / "package-c"],
            REPO_ROOT / "eval" / "golden" / "day11-multihop.jsonl",
            modes=("hybrid-graph",),
        )


def test_mode_registry_and_fusion_shape() -> None:
    """hybrid-graph fuses three routes under one RRF (constructed offline)."""
    from learnarken.retrieval import GRAPH_MODES, MODES, _mode_retriever

    assert set(GRAPH_MODES) <= set(MODES)
    chunks = chunk_package(PACKAGE_A)
    ensemble = _mode_retriever("hybrid-graph", chunks, k=10, strategy="structure")
    assert len(ensemble.retrievers) == 3
    assert ensemble.weights == [1 / 3, 1 / 3, 1 / 3]
    assert ensemble.id_key == "chunk_id"


def test_ablation_default_modes_exclude_graph() -> None:
    """Red-team #9: the pre-Day-11 ablation command must not silently gain a
    Neo4j dependency — graph modes are opt-in via --modes, not the default."""
    from learnarken.retrieval import DEFAULT_ABLATION_MODES, GRAPH_MODES

    assert not set(DEFAULT_ABLATION_MODES) & set(GRAPH_MODES)


# --- Corpus-authoritative sync (red-team day11 #1) -------------------------


def test_sync_cleans_up_edges_index_and_dms_no_longer_asserted(monkeypatch) -> None:
    """A DM/edge/ICN from a *previous* sync that the current chunk set no
    longer asserts must be scrubbed in the same sync, not survive as stale
    graph state that a later `hybrid-graph` query could silently ride on."""
    from learnarken.chunking.base import Chunk

    captured: list[tuple[str, dict]] = []

    def fake_cypher(statements):
        captured.extend(statements)
        return [{"data": []} for _ in statements]

    monkeypatch.setattr(store, "_cypher", fake_cypher)
    chunk = Chunk(
        chunk_id="c1",
        strategy="structure",
        dmc="DM-A",
        dm_title="Title A",
        issue_info="",
        chunk_type="description",
        source_path="/x",
        text="t",
        outbound_dm_refs=["DM-B"],
        icn_refs=["ICN-1"],
    )
    store.sync([chunk], owner={"c1": "pkg"})

    delete_stmts = [s for s, _ in captured if "DELETE" in s or "REMOVE" in s]
    assert any("REFS" in s and "WHERE NOT t.dmc IN $refs" in s for s in delete_stmts)
    assert any("USES_ICN" in s and "WHERE NOT i.ident IN $icns" in s for s in delete_stmts)
    assert any("WHERE NOT d.dmc IN $known DETACH DELETE d" in s for s in delete_stmts)
    assert any("WHERE NOT i.ident IN $known DETACH DELETE i" in s for s in delete_stmts)
    assert any("REMOVE d.package" in s for s in delete_stmts)
    # The known-node set must include the referenced (dangling) DM, so the
    # cleanup does not delete a legitimately-dangling reference target.
    known_params = next(p for s, p in captured if "DETACH DELETE d" in s)
    assert "DM-B" in known_params["known"]


def test_stats_parses_counts(monkeypatch) -> None:
    def fake_cypher(statements):
        return [{"data": [{"row": [n]}]} for n in (3, 5, 2)]

    monkeypatch.setattr(store, "_cypher", fake_cypher)
    assert store.stats() == {"dm_nodes": 3, "edges": 7}


def test_stats_fails_closed_on_malformed_response(monkeypatch) -> None:
    monkeypatch.setattr(store, "_cypher", lambda statements: [{"data": []} for _ in statements])
    with pytest.raises(store.GraphError):
        store.stats()


def test_neighborhood_rejects_over_broad_seed_list() -> None:
    """Red-team #2: the node cap bounds discovery, not the seed list itself —
    an over-broad entity link (e.g. a very common task phrase) must be cut
    before it reaches Neo4j."""
    too_many = [f"DM-{i}" for i in range(store.MAX_EXPAND_SEEDS + 1)]
    with pytest.raises(ValueError, match="MAX_EXPAND_SEEDS"):
        store.neighborhood(too_many, depth=1)


def test_answer_trace_preserves_graph_span_alongside_facts(monkeypatch, tmp_path) -> None:
    """Red-team #5: `spans["graph"]` (entities/candidates, set before the
    threshold gate) must survive to an *answered* trace, not be clobbered by
    the interface-③ `facts` span written after the gate. Hermetic: mocks the
    same seams as tests/test_day5_answer.py's `wired` fixture."""
    import json

    from learnarken.answer import engine
    from learnarken.chunking.base import Chunk
    from learnarken.chunking.documents import to_document
    from learnarken.graph.store import GraphFacts
    from learnarken.retrieval import hybrid as hybrid_module

    monkeypatch.chdir(tmp_path)
    chunk = Chunk(
        chunk_id="c1",
        strategy="structure",
        dmc="DMC-LA100-A-29-10-00-00A-520A-A",
        dm_title="Hydraulic pump",
        issue_info="",
        chunk_type="step",
        source_path="/x",
        text="Release the pressure.",
    )
    graph_document = to_document(chunk)
    graph_document.metadata["graph_hop"] = 1
    graph_document.metadata["graph_direction"] = "out"
    monkeypatch.setattr(engine, "corpus_chunks", lambda pkg, strategy: [chunk])
    monkeypatch.setattr(engine, "verify_corpus", lambda c, s: None)
    monkeypatch.setattr(engine, "load_threshold", lambda: 0.5)
    monkeypatch.setattr(engine, "_candidates", lambda question, c, mode: [graph_document])
    monkeypatch.setattr(
        hybrid_module, "rerank_scored", lambda query, documents, k=10: [(graph_document, 0.9)]
    )
    monkeypatch.setattr(
        engine.graph, "facts", lambda dmcs: [GraphFacts(dmc=d, title="t") for d in dmcs]
    )

    def fake_chat(system, user, **kwargs):
        from learnarken.llm.minimax import ChatResult

        return ChatResult(
            parsed={
                "is_answerable": True,
                "answer": "Release pressure.",
                "citations": [{"chunk_id": "c1", "supporting_quote": "Release the pressure."}],
            },
            raw_content="{}",
            model="MiniMax-M3",
            usage={"total_tokens": 1},
            request_payload={"messages": []},
        )

    monkeypatch.setattr(engine, "chat_json", fake_chat)

    result = engine.answer_question("tell me about the hydraulic pump", mode="hybrid-graph")
    assert not result.refused
    trace = json.loads((tmp_path / "eval" / "traces" / f"{result.trace_id}.json").read_text())
    assert trace["graph"]["entities"], "linked entities must survive to the answered trace"
    assert trace["graph"]["candidates"] == [{"chunk_id": "c1", "hop": 1, "direction": "out"}]
    assert trace["graph"]["facts"][0]["dmc"] == chunk.dmc  # merged, not overwritten


def test_neighborhood_surfaces_malformed_response_as_graph_error(monkeypatch) -> None:
    """Red-team #7: an unexpected response shape (wrong service, proxy) must
    degrade the search path via GraphError, not crash with KeyError/TypeError."""

    def bad_shape(statements):
        return [{"data": [{"row": ["only-one-field"]}]}]  # missing the neighbor list

    monkeypatch.setattr(store, "_cypher", bad_shape)
    with pytest.raises(store.GraphError):
        store.neighborhood(["X"], depth=1)


# --- day11_refusal_gate.py fail-closed path (red-team #11 residual gap) ----


def _load_refusal_gate_module():
    import importlib.util

    path = REPO_ROOT / "tools" / "day11_refusal_gate.py"
    spec = importlib.util.spec_from_file_location("day11_refusal_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refusal_gate_fails_closed_when_neo4j_down(monkeypatch) -> None:
    """The gate must refuse to run — not silently measure an empty graph
    arm — when Neo4j is unreachable (red-team #3, now with pytest coverage
    per the #11 residual gap). Hermetic: Neo4j is checked before any Vespa
    access, so this needs no live services."""
    module = _load_refusal_gate_module()
    monkeypatch.setattr(module.graph, "is_up", lambda: False)
    with pytest.raises(SystemExit, match="Neo4j is unreachable"):
        module.main()
