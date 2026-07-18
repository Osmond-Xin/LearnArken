"""Day 9 evidence-chain guards (spec Decision 3) + dependency-impact query.

Two invariants keep the machine-readable evidence chain honest:
  - **No dead / escaping links** — every repo path referenced by EVIDENCE.md /
    llms.txt exists AND resolves inside the repo (DR pitfall #2; and INV-1: a
    link must not reach a private file outside the repo — day9 red-team #4).
  - **No number drift** — every metric-like number in EVIDENCE.md is registered,
    and the pinned ones match their source artifact (DR pitfall #3; day9 #2:
    unregistered numbers now fail rather than passing unchecked).

Plus the graph-impact query (ADR-0002 interface ①): depth validation, fail-closed
parsing, and the BFS traversal (cycle-safety, direction, hop distances) are tested
hermetically against a fake transport; live Neo4j tests run when the container is
up (self-contained fixture, cleaned up).
"""

from __future__ import annotations

import json
import re
import urllib.error
from pathlib import Path

import pytest

from learnarken import graph
from learnarken.graph import store

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_FILES = [REPO_ROOT / "llms.txt", REPO_ROOT / "docs" / "EVIDENCE.md"]
_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _links(path: Path) -> list[str]:
    return _LINK.findall(path.read_text(encoding="utf-8"))


# --- Dead-link + repo-boundary guard (#4) ----------------------------------


@pytest.mark.parametrize("doc", DOC_FILES, ids=lambda p: p.name)
def test_links_live_and_repo_internal(doc: Path) -> None:
    """Every relative link resolves to a real path *inside* the repo.

    Existence alone is not enough: a link like `../resume-master/resume.md` could
    exist on a dev machine, which would leak the INV-1 private boundary — so we
    also require the resolved target to sit under REPO_ROOT.
    """
    assert doc.is_file(), f"{doc} is missing"
    broken, escaping = [], []
    for link in _links(doc):
        if link.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target = (doc.parent / link.split("#", 1)[0]).resolve()
        if not target.exists():
            broken.append(link)
            continue
        try:
            target.relative_to(REPO_ROOT)
        except ValueError:
            escaping.append(link)
    assert not broken, f"dead links in {doc.name}: {broken}"
    assert not escaping, f"links escape the repo (INV-1 risk) in {doc.name}: {escaping}"


# --- Number-drift guard (#2) -----------------------------------------------

_KAPPA = "eval/results/day8-kappa.json"
_ABLATION = "eval/results/day4-ablation.json"
_BAKEOFF = "eval/results/day4-bakeoff.json"

# Pinned numbers: substring that must appear in EVIDENCE.md, source json, key
# path, expected value, decimals. These are additionally checked against source.
NUMBER_CHECKS = [
    ("Codex `κ 0.737`", _KAPPA, ("judges", "codex", "kappa"), 0.737, 3),
    ("agy `κ 0.667`", _KAPPA, ("judges", "agy", "kappa"), 0.667, 3),
    ("`Recall@10 1.00`", _ABLATION, ("results", "dense", "recall@10"), 1.00, 2),
    ("`Recall@5 0.99`", _ABLATION, ("results", "dense", "recall@5"), 0.99, 2),
    ("`nDCG@10 0.90`", _ABLATION, ("results", "dense", "ndcg@10"), 0.90, 2),
    ("`Recall@5 0.83`", _ABLATION, ("results", "bm25", "recall@5"), 0.83, 2),
    ("`Recall@10 0.88`", _ABLATION, ("results", "bm25", "recall@10"), 0.88, 2),
    ("Qwen3 `Recall@5 0.99", _BAKEOFF, ("results", "qwen3-8b", "overall", "recall@5"), 0.99, 2),
    ("BGE-M3 `0.92 / 0.97`", _BAKEOFF, ("results", "bge-m3", "overall", "recall@5"), 0.92, 2),
    ("BGE-M3 `0.92 / 0.97`", _BAKEOFF, ("results", "bge-m3", "overall", "recall@10"), 0.97, 2),
]

# Numbers with no static artifact (service-reproduced or behavioural) — registered
# but not pinned. Every metric-like number in EVIDENCE.md must be in the union of
# these and the NUMBER_CHECKS values, else the drift guard fails (day9 #2).
DYNAMIC_NUMBERS = {"0.93", "0.83", "0.40", "0.53", "0.63", "3/3", "0/3"}
_PINNED_TOKENS = {f"{exp:.{dec}f}" for _, _, _, exp, dec in NUMBER_CHECKS}
_METRIC_TOKEN = re.compile(r"`[^`]*`")
_DECIMAL = re.compile(r"\d+\.\d{2,3}")
_FRACTION = re.compile(r"\d/\d")


def _dig(obj: dict, path: tuple[str, ...]):
    for key in path:
        obj = obj[key]
    return obj


@pytest.mark.parametrize("substr, src, keypath, expected, decimals", NUMBER_CHECKS)
def test_evidence_numbers_match_source(substr, src, keypath, expected, decimals) -> None:
    """Pinned numbers stated in EVIDENCE.md equal the frozen artifact they cite."""
    evidence = (REPO_ROOT / "docs" / "EVIDENCE.md").read_text(encoding="utf-8")
    assert substr in evidence, f"EVIDENCE.md no longer states {substr!r}"
    data = json.loads((REPO_ROOT / src).read_text(encoding="utf-8"))
    actual = round(float(_dig(data, keypath)), decimals)
    assert actual == expected, f"{src}:{'.'.join(keypath)} = {actual}, EVIDENCE says {expected}"


def test_no_unregistered_numbers_in_evidence() -> None:
    """Every metric-like number in EVIDENCE.md is registered (pinned or dynamic).

    Closes the coverage gap flagged in the day9 red team: a new number can no
    longer appear unchecked — it must be pinned to an artifact or explicitly
    listed as service-reproduced.
    """
    evidence = (REPO_ROOT / "docs" / "EVIDENCE.md").read_text(encoding="utf-8")
    registered = _PINNED_TOKENS | DYNAMIC_NUMBERS
    found: set[str] = set()
    for span in _METRIC_TOKEN.findall(evidence):
        found.update(_DECIMAL.findall(span))
        found.update(_FRACTION.findall(span))
    unregistered = found - registered
    assert not unregistered, (
        f"unregistered numbers in EVIDENCE.md: {sorted(unregistered)} — pin them "
        "to a source artifact in NUMBER_CHECKS or add to DYNAMIC_NUMBERS"
    )


def test_adversarial_set_size_matches_golden() -> None:
    """The `32`-case claim equals the golden file's line count."""
    evidence = (REPO_ROOT / "docs" / "EVIDENCE.md").read_text(encoding="utf-8")
    assert "`32` cases" in evidence
    golden = (REPO_ROOT / "eval" / "golden" / "day8-adversarial.jsonl").read_text(encoding="utf-8")
    assert sum(1 for line in golden.splitlines() if line.strip()) == 32


# --- Graph impact query: hermetic (fake transport) -------------------------

# A fixture graph over REFS edges (referrer)-[:REFS]->(target):
#   C->B, B->A, A->X, plus an A<->B VIO-7 cycle (A->B). Reverse-impact of X is
#   {A(1), B(2), C(3)}; the cycle must not loop and X must never list itself.
_FAKE_EDGES = {("A", "X"), ("B", "A"), ("C", "B"), ("A", "B")}
_FAKE_NODES = {a for a, _ in _FAKE_EDGES} | {b for _, b in _FAKE_EDGES}


def _fake_cypher(statements):
    stmt, params = statements[0]
    if "count(x)" in stmt:
        dmc = params["dmc"]
        n = 1 if dmc in _FAKE_NODES else 0
        pkg = "pkg" if n else None
        return [{"data": [{"row": [n, pkg]}] if n else []}]
    frontier, visited = set(params["frontier"]), set(params["visited"])
    hits = sorted(a for (a, t) in _FAKE_EDGES if t in frontier and a not in visited)
    return [{"data": [{"row": [a, f"{a}-title"]} for a in hits]}]


@pytest.fixture
def fake_transport(monkeypatch):
    monkeypatch.setattr(store, "_cypher", _fake_cypher)


def test_impact_bfs_transitive_direction_and_cycle_safe(fake_transport) -> None:
    """Real BFS logic over a fake graph: transitivity, hop distance, direction,
    and cycle-safety — covered without a live Neo4j (day9 #5)."""
    result = store.impact("X", depth=store.MAX_IMPACT_DEPTH)
    hops = {d.dmc: d.hops for d in result.affected}
    assert hops == {"A": 1, "B": 2, "C": 3}  # transitive, shortest hops
    assert "X" not in hops  # never lists itself despite the A<->B cycle
    assert result.exists_in_corpus and result.exists_as_reference


def test_impact_bfs_respects_depth(fake_transport) -> None:
    result = store.impact("X", depth=1)
    assert {d.dmc for d in result.affected} == {"A"}  # only A->X is direct


def test_impact_direction_is_reverse(fake_transport) -> None:
    """Impact walks *into* the target; X refers to nothing, so X impacts nobody
    only if asked about a sink — asking about A (which X's referrers point to)."""
    # 'X' is a sink (refers to nothing); nobody is a referent-of-X, but referrers
    # exist. A wrong (forward) direction would return X's referents = none.
    assert store.impact("X", depth=3).affected  # non-empty proves reverse direction


def test_impact_unknown_dm(fake_transport) -> None:
    result = store.impact("ZZZ", depth=3)
    assert result.exists_as_reference is False
    assert result.exists_in_corpus is False
    assert result.affected == []


def test_impact_dangling_reference_distinguished(monkeypatch) -> None:
    """A referenced-but-not-indexed DM (bare node, no package) reports as a
    reference, not a corpus module (day9 #6)."""

    def _dangling(statements):
        stmt, _ = statements[0]
        if "count(x)" in stmt:
            return [{"data": [{"row": [1, None]}]}]  # exists as node, no package
        return [{"data": []}]

    monkeypatch.setattr(store, "_cypher", _dangling)
    result = store.impact("DMC-MISSING", depth=3)
    assert result.exists_as_reference is True
    assert result.exists_in_corpus is False


# --- Graph store: fail-closed parsing (#3) ---------------------------------


@pytest.mark.parametrize("bad_depth", [0, store.MAX_IMPACT_DEPTH + 1, 3.0, "3"])
def test_impact_depth_is_bounded_and_typed(bad_depth) -> None:
    """Depth must be an int in range, validated before any query (hermetic)."""
    with pytest.raises(ValueError, match="depth must be"):
        store.impact("DMC-ANY", depth=bad_depth)


def test_impact_fails_closed_when_neo4j_unreachable(monkeypatch) -> None:
    """A transport failure surfaces as GraphError, never a silent empty result."""

    def _boom(*_args, **_kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(store.urllib.request, "urlopen", _boom)
    with pytest.raises(graph.GraphError):
        store.impact("DMC-ANY", depth=3)


def test_cypher_fails_closed_on_non_json(monkeypatch) -> None:
    """A non-Neo4j service answering 200 with HTML fails closed, not a stack trace."""

    class _Resp:
        def read(self):
            return b"<html>not neo4j</html>"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: _Resp())
    with pytest.raises(graph.GraphError, match="non-JSON"):
        store._cypher([("RETURN 1", {})])


def test_cypher_fails_closed_on_result_count_mismatch(monkeypatch) -> None:
    """A degraded endpoint returning 200 `{}` (no results) fails closed."""

    class _Resp:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: _Resp())
    with pytest.raises(graph.GraphError, match="expected 1 result"):
        store._cypher([("RETURN 1", {})])


# --- Graph impact query: live Neo4j (integration) --------------------------

needs_neo4j = pytest.mark.skipif(not graph.is_up(), reason="needs the learnarken-neo4j container")
_PREFIX = "TEST-DAY9-"


@pytest.fixture
def cyclic_graph():
    """Isolated live-Neo4j fixture, torn down regardless of assertion outcome."""
    store._cypher(
        [
            (
                "MERGE (x:DM {dmc:$x}) MERGE (a:DM {dmc:$a}) MERGE (b:DM {dmc:$b}) "
                "MERGE (c:DM {dmc:$c}) "
                "SET a.package='t', b.package='t', c.package='t', x.package='t' "
                "MERGE (a)-[:REFS]->(x) MERGE (b)-[:REFS]->(a) MERGE (c)-[:REFS]->(b) "
                "MERGE (b)-[:REFS]->(a) MERGE (a)-[:REFS]->(b)",  # A<->B cycle
                {"x": f"{_PREFIX}X", "a": f"{_PREFIX}A", "b": f"{_PREFIX}B", "c": f"{_PREFIX}C"},
            )
        ]
    )
    try:
        yield
    finally:
        store._cypher([(f"MATCH (d:DM) WHERE d.dmc STARTS WITH '{_PREFIX}' DETACH DELETE d", {})])


@needs_neo4j
def test_impact_live_transitive_and_cycle_safe(cyclic_graph) -> None:
    """The BFS behaves identically against a real Neo4j."""
    result = store.impact(f"{_PREFIX}X", depth=store.MAX_IMPACT_DEPTH)
    hops = {d.dmc: d.hops for d in result.affected}
    assert hops == {f"{_PREFIX}A": 1, f"{_PREFIX}B": 2, f"{_PREFIX}C": 3}
    assert f"{_PREFIX}X" not in hops
    assert result.exists_in_corpus is True
