"""Retrieval metrics over a versioned golden set (Day 3).

Metric priority follows tutorial 02 §4: Recall@k leads for RAG (the LLM can
only ground on evidence inside the top-k), nDCG measures ranking quality, MRR
is the single-answer view. Relevance is annotated at the (DMC, source_path)
anchor level; a chunk counts relevant when it shares the DMC and its text
contains — or is contained by — the anchor's text, so one annotation serves
both the structure and recursive strategies.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

from learnarken.chunking.base import Chunk
from learnarken.loader import _text, load_data_module, parse_file

logger = logging.getLogger("learnarken")


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
        queries.append(
            GoldenQuery(
                query_id=row["query_id"],
                query=row["query"],
                relevant=[(r["dmc"], r["source_path"]) for r in row.get("relevant", [])],
            )
        )
    return queries


def resolve_anchor_texts(
    package_dirs: list[str | Path], anchors: set[tuple[str, str]]
) -> dict[tuple[str, str], str]:
    """Map each (dmc, xpath) anchor to the normalized text of that element."""
    wanted_by_dmc: dict[str, set[str]] = {}
    for dmc, xpath in anchors:
        wanted_by_dmc.setdefault(dmc, set()).add(xpath)

    texts: dict[tuple[str, str], str] = {}
    for package_dir in package_dirs:
        for path in sorted(Path(package_dir).glob("DMC-*.xml")):
            try:
                tree = parse_file(path)[0]
                dmc = load_data_module(path, tree.getroot()).dmc
            except Exception as exc:  # noqa: BLE001
                logger.warning("resolve_anchor_texts: skipping %s (%s)", path.name, exc)
                continue
            for xpath in wanted_by_dmc.get(dmc, ()):
                found = tree.xpath(xpath)
                if found:
                    texts[(dmc, xpath)] = _text(found[0])
    missing = anchors - texts.keys()
    for anchor in missing:
        logger.warning("golden anchor did not resolve to any element: %s", anchor)
    return texts


def _relevant_chunk_ids(
    query: GoldenQuery, chunks: list[Chunk], anchor_texts: dict[tuple[str, str], str]
) -> set[str]:
    ids: set[str] = set()
    for dmc, xpath in query.relevant:
        anchor_text = anchor_texts.get((dmc, xpath))
        if not anchor_text:
            continue
        for c in chunks:
            if c.dmc == dmc and (anchor_text in c.text or c.text in anchor_text):
                ids.add(c.chunk_id)
    return ids


def _dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def evaluate_strategy(
    chunks: list[Chunk],
    search,
    golden: list[GoldenQuery],
    anchor_texts: dict[tuple[str, str], str],
    ks: tuple[int, ...] = (5, 10),
) -> dict[str, float]:
    """Average metrics across queries with at least one resolvable relevant chunk."""
    top = max(ks + (10,))
    recall = {k: 0.0 for k in ks}
    mrr_sum = ndcg_sum = 0.0
    evaluated = 0
    for q in golden:
        relevant = _relevant_chunk_ids(q, chunks, anchor_texts)
        if not relevant:
            continue
        evaluated += 1
        ranked = [sc.chunk.chunk_id for sc in search(q.query, k=top)]
        hits = [1 if cid in relevant else 0 for cid in ranked]
        for k in ks:
            recall[k] += sum(hits[:k]) / len(relevant)
        first = next((i for i, h in enumerate(hits) if h), None)
        mrr_sum += 1.0 / (first + 1) if first is not None else 0.0
        ndcg_k = max(ks)
        idcg = _dcg([1] * min(len(relevant), ndcg_k))
        ndcg_sum += (_dcg(hits[:ndcg_k]) / idcg) if idcg else 0.0

    n = evaluated or 1
    result = {f"recall@{k}": round(recall[k] / n, 4) for k in ks}
    result["mrr"] = round(mrr_sum / n, 4)
    result[f"ndcg@{max(ks)}"] = round(ndcg_sum / n, 4)
    result["n_evaluated"] = evaluated
    return result
