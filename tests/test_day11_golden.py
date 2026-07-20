"""Day 11 multi-hop golden set: schema, anchor resolution, connectivity claims.

The connectivity check re-derives the REFS edge list from the sample XML
(dmRef parsing), so the golden file's `graph_connected` flags are verified
against the corpus, not trusted (T4: the worksheet's expected paths are
claims). No live services needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from lxml import etree

from learnarken.retrieval.evaluate import load_golden, resolve_anchors, unresolved_anchors

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN = REPO_ROOT / "eval" / "golden" / "day11-multihop.jsonl"
PACKAGES = [REPO_ROOT / "samples" / "package-a", REPO_ROOT / "samples" / "package-c"]


def _rows() -> list[dict]:
    return [
        json.loads(line)
        for line in GOLDEN.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _refs_edges() -> set[tuple[str, str]]:
    """(source DMC, target DMC) from dmRef elements in the sample packages."""

    def code(dc) -> str:
        keys = (
            "modelIdentCode",
            "systemDiffCode",
            "systemCode",
            "subSystemCode",
            "subSubSystemCode",
            "assyCode",
            "disassyCode",
            "disassyCodeVariant",
            "infoCode",
            "infoCodeVariant",
            "itemLocationCode",
        )
        a = dc.attrib
        return (
            f"DMC-{a[keys[0]]}-{a[keys[1]]}-{a[keys[2]]}-{a[keys[3]]}{a[keys[4]]}-"
            f"{a[keys[5]]}-{a[keys[6]]}{a[keys[7]]}-{a[keys[8]]}{a[keys[9]]}-{a[keys[10]]}"
        )

    edges: set[tuple[str, str]] = set()
    for pkg in PACKAGES:
        for path in sorted(pkg.glob("DMC-*.xml")):
            root = etree.parse(str(path)).getroot()
            source = code(root.find(".//dmIdent/dmCode"))
            for ref in root.findall(".//dmRef//dmCode"):
                edges.add((source, code(ref)))
    return edges


def test_schema_loads_and_counts() -> None:
    golden = load_golden(GOLDEN)
    assert len(golden) == 10
    assert sum(1 for q in golden if q.relevant) == 7  # MH-01..07
    assert sum(1 for q in golden if not q.relevant) == 3  # traps MH-08..10
    texts = [q.query for q in golden]
    assert len(set(texts)) == len(texts)


def test_provenance_flags_present() -> None:
    for row in _rows():
        assert row["human_authored"] is True
        assert row["ai_formatted"] is True
        assert row["category"] in ("multi_hop", "no_answer")


def test_all_anchors_resolve_in_corpus() -> None:
    golden = load_golden(GOLDEN)
    anchors = {a for q in golden for a in q.relevant}
    resolved = resolve_anchors(PACKAGES, anchors)
    assert unresolved_anchors(anchors, resolved) == set()


def test_multihop_rows_span_multiple_dms() -> None:
    for row in _rows():
        if row["category"] != "multi_hop":
            continue
        dms = {r["dmc"] for r in row["relevant"]}
        assert len(dms) >= 2, f"{row['query_id']} is not multi-DM"
        assert row["hops"] == len(dms), f"{row['query_id']} hops field drifted"


@pytest.mark.parametrize("row", [r for r in _rows() if r["category"] == "multi_hop"])
def test_graph_connected_flags_match_corpus(row) -> None:
    """`graph_connected` must equal reality: anchor DMs in one undirected REFS
    component (paths may pass through non-anchor DMs). MH-04's disconnection is
    asserted, not just tolerated — the honesty flag must not drift."""
    edges = _refs_edges()
    adjacency: dict[str, set[str]] = {}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    dms = {r["dmc"] for r in row["relevant"]}
    start = sorted(dms)[0]
    seen = {start}
    frontier = [start]
    while frontier:
        fresh = {n for d in frontier for n in adjacency.get(d, ()) if n not in seen}
        seen |= fresh
        frontier = sorted(fresh)
    connected = dms <= seen
    assert connected is row["graph_connected"], (
        f"{row['query_id']}: graph_connected={row['graph_connected']} but corpus says {connected}"
    )


def test_trap_rows_document_their_trap() -> None:
    for row in _rows():
        if row["category"] == "no_answer":
            assert row["relevant"] == []
            assert row.get("trap_note"), f"{row['query_id']} missing trap_note"
