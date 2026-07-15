"""Retrieval metrics over a versioned golden set (Day 3).

Metric priority follows tutorial 02 §4: Recall@k leads for RAG (the LLM can
only ground on evidence inside the top-k), nDCG measures ranking quality, MRR
is the single-answer view. Relevance is annotated at the (DMC, source_path)
anchor level. A **structure** chunk matches when it shares the DMC and its
XPath equals or nests with the anchor's XPath (exact, no text false
positives); a **recursive** chunk — which has no XPath — matches when it shares
the DMC and its window text contains the anchor element's text. No-answer
queries (empty `relevant`) are scored separately as a refusal/zero-hit metric.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from learnarken.chunking.base import Chunk
from learnarken.loader import _text, load_data_module, parse_file
from learnarken.retrieval.bm25 import tokenize

logger = logging.getLogger("learnarken")

# Fraction of an anchor's tokens that must appear in a recursive window for it to
# count as covering the anchor — tolerates an anchor split across two windows,
# where full-string containment would spuriously miss (red-team R3).
_RECURSIVE_OVERLAP = 0.6


@dataclass
class GoldenQuery:
    query_id: str
    query: str
    relevant: list[tuple[str, str]]  # (dmc, source_path) anchors


def load_golden(path: str | Path) -> list[GoldenQuery]:
    queries: list[GoldenQuery] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"golden row must be a JSON object: {line[:80]}")
        for key in ("query_id", "query", "relevant"):
            if key not in row:
                raise ValueError(f"golden row missing required key {key!r}: {line[:80]}")
        if not (isinstance(row["query_id"], str) and isinstance(row["query"], str)):
            raise ValueError(f"golden 'query_id'/'query' must be strings: {line[:80]}")
        if not isinstance(row["relevant"], list):
            raise ValueError(
                f"golden 'relevant' must be a list (use [] for no-answer): {line[:80]}"
            )
        relevant: list[tuple[str, str]] = []
        for item in row["relevant"]:
            if not (isinstance(item, dict) and "dmc" in item and "source_path" in item):
                raise ValueError(f"golden 'relevant' items must be {{dmc, source_path}}: {item!r}")
            if not (isinstance(item["dmc"], str) and isinstance(item["source_path"], str)):
                raise ValueError(f"golden 'dmc'/'source_path' must be strings: {item!r}")
            relevant.append((item["dmc"], item["source_path"]))
        queries.append(GoldenQuery(row["query_id"], row["query"], relevant))
    return queries


@dataclass
class ResolvedAnchor:
    canonical_path: str  # lxml getpath of the element (chunk source_paths use the same convention)
    text: str


def resolve_anchors(
    package_dirs: list[str | Path], anchors: set[tuple[str, str]]
) -> dict[tuple[str, str], ResolvedAnchor]:
    """Resolve each (dmc, xpath) anchor to the element's canonical getpath + text.

    Canonicalizing via getpath makes matching robust to equivalent XPath
    spellings — e.g. a golden `levelledPara[1]` resolves to the same canonical
    path as the chunk's `levelledPara` when the element is unique.
    """
    wanted_by_dmc: dict[str, set[str]] = {}
    for dmc, xpath in anchors:
        wanted_by_dmc.setdefault(dmc, set()).add(xpath)

    resolved: dict[tuple[str, str], ResolvedAnchor] = {}
    for package_dir in package_dirs:
        for path in sorted(Path(package_dir).glob("DMC-*.xml")):
            try:
                tree = parse_file(path)[0]
                dmc = load_data_module(path, tree.getroot()).dmc
            except Exception as exc:  # noqa: BLE001
                logger.warning("resolve_anchors: skipping %s (%s)", path.name, exc)
                continue
            for xpath in wanted_by_dmc.get(dmc, ()):
                try:
                    found = tree.xpath(xpath)
                except etree.XPathError as exc:
                    logger.warning("golden anchor xpath is invalid (%s): %s", xpath, exc)
                    continue
                # A non-list result (count()/string() XPath) can't be an element
                # anchor — treat as unresolved rather than crashing on len() (R5).
                if not isinstance(found, list):
                    logger.warning("golden anchor %s is not an element selector", xpath)
                    continue
                # Require exactly one element: a broad selector matching several
                # steps would silently bind to the first (red-team R2), so treat
                # ambiguous/empty/non-element results as unresolved → fail closed.
                if len(found) == 1 and isinstance(found[0], etree._Element):
                    resolved[(dmc, xpath)] = ResolvedAnchor(tree.getpath(found[0]), _text(found[0]))
                elif len(found) > 1:
                    logger.warning(
                        "golden anchor %s matched %d elements (ambiguous)", xpath, len(found)
                    )
    return resolved


def unresolved_anchors(
    anchors: set[tuple[str, str]], resolved: dict[tuple[str, str], ResolvedAnchor]
) -> set[tuple[str, str]]:
    """Anchors that did not resolve to an element in the corpus (golden ↔ corpus drift)."""
    return anchors - resolved.keys()


def _xpath_related(a: str, b: str) -> bool:
    """True if XPaths are equal or one nests within the other (ancestor/descendant)."""
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _anchor_chunk_sets(
    query: GoldenQuery, chunks: list[Chunk], resolved: dict[tuple[str, str], ResolvedAnchor]
) -> list[set[str]]:
    """One chunk-id set per golden anchor (empty set = that anchor maps to no chunk).

    Keeping anchors separate means a query with two relevant anchors, only one of
    which maps to a chunk, still counts both in the denominator — a missing anchor
    cannot silently inflate recall (red-team R5).
    """
    sets: list[set[str]] = []
    for dmc, xpath in query.relevant:
        anchor = resolved.get((dmc, xpath))
        ids: set[str] = set()
        if anchor is not None:
            anchor_tokens = set(tokenize(anchor.text)) if anchor.text else set()
            for c in chunks:
                if c.dmc != dmc:
                    continue
                if c.strategy == "recursive":
                    # ≥0.6 token overlap AND ≥2 shared tokens over a ≥2-token
                    # anchor, so a single generic token can't match (R4/R5).
                    shared = anchor_tokens & set(tokenize(c.text))
                    if (
                        len(anchor_tokens) >= 2
                        and len(shared) >= 2
                        and len(shared) / len(anchor_tokens) >= _RECURSIVE_OVERLAP
                    ):
                        ids.add(c.chunk_id)
                elif _xpath_related(c.source_path, anchor.canonical_path):
                    ids.add(c.chunk_id)
        sets.append(ids)
    return sets


def _dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def evaluate_strategy(
    chunks: list[Chunk],
    search,
    golden: list[GoldenQuery],
    resolved: dict[tuple[str, str], ResolvedAnchor],
    ks: tuple[int, ...] = (5, 10),
) -> dict[str, float]:
    """Ranking metrics over answerable queries + a no-answer refusal metric.

    No-answer queries (empty `relevant`) are scored as "returned zero hits" so a
    retriever that hallucinates results for out-of-corpus questions is penalized
    rather than silently ignored (red-team #3).
    """
    top = max(ks + (10,))
    recall = {k: 0.0 for k in ks}
    mrr_sum = ndcg_sum = 0.0
    answerable = unmapped = 0
    no_answer_total = zero_hit = 0
    for q in golden:
        if not q.relevant:
            no_answer_total += 1
            if not search(q.query, k=top):
                zero_hit += 1
            continue
        answerable += 1
        anchor_sets = _anchor_chunk_sets(q, chunks, resolved)  # one set per anchor
        total = len(anchor_sets)  # unmapped anchors stay in the denominator
        if not any(anchor_sets):
            # Every anchor maps to no chunk (a chunking coverage gap): count as
            # answerable with zero recall (no denominator shrink) — fail closed,
            # not flattered (red-team R2).
            unmapped += 1
            logger.warning("query %s: resolved anchor maps to no chunk — scored zero", q.query_id)
            continue
        ranked = [sc.chunk.chunk_id for sc in search(q.query, k=top)]
        for k in ks:
            covered = sum(1 for s in anchor_sets if s & set(ranked[:k]))
            recall[k] += covered / total
        first = next(
            (i for i, cid in enumerate(ranked) if any(cid in s for s in anchor_sets)), None
        )
        mrr_sum += 1.0 / (first + 1) if first is not None else 0.0
        ndcg_k = max(ks)
        credited: set[int] = set()
        gains: list[int] = []
        for cid in ranked[:ndcg_k]:
            gain = 0
            for idx, s in enumerate(anchor_sets):
                if idx not in credited and cid in s:
                    credited.add(idx)
                    gain = 1
                    break
            gains.append(gain)
        idcg = _dcg([1] * min(total, ndcg_k))
        ndcg_sum += (_dcg(gains) / idcg) if idcg else 0.0

    n = answerable or 1
    result: dict[str, float] = {f"recall@{k}": round(recall[k] / n, 4) for k in ks}
    result["mrr"] = round(mrr_sum / n, 4)
    result[f"ndcg@{max(ks)}"] = round(ndcg_sum / n, 4)
    result["n_evaluated"] = answerable
    result["n_unmapped"] = unmapped
    result["n_no_answer"] = no_answer_total
    # Honest name: this is the zero-lexical-hit rate on no-answer queries, not a
    # true abstention-quality score (BM25 has no refusal logic — Day 5/8).
    result["zero_hit_rate"] = round(zero_hit / (no_answer_total or 1), 4)
    return result
