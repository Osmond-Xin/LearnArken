"""Query-time figure second-look wiring (Day 12, docs/specs/day12.md §4, G15).

When a figure chunk is the evidence but the (declared-grounded) description did
not answer the question, the agent re-reads the actual image with a **multi-
sample consensus read** (`second_look.consensus_read`) before refusing. Two
honest constraints shape what this does at toy scale:

- the indexed figure text is already the *complete verified declared set*, so a
  re-read cannot surface new **verified** content the description lacked;
- answering from an *un*verified re-read would reintroduce exactly the
  unverified-VLM-text risk the red-team had us remove (P1c).

So second-look's role here is a **consensus-gated confirmation feeding the G15
fail-closed refusal**: it re-reads (guarding against a single flaky read), records
the outcome in the trace, and the answer refuses `figure-out-of-description`
rather than guess. (Answering from a re-read for genuinely lossy real-world
figures is Roadmap.)
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from learnarken.chunking.base import Chunk
from learnarken.multimodal import ingest
from learnarken.multimodal.second_look import (
    QUOTA_EXHAUSTED,
    FigureRefusal,
    consensus_read,
)


def _load_asset(
    icn_id: str, package_dirs: list[str], owner_dmc: str = ""
) -> tuple[ingest.FigureRecord, bytes] | None:
    """Resolve the figure asset for `icn_id`, owned by `owner_dmc`.

    Matching on the ICN alone picks the first package that happens to carry that
    ident — which may not be the package the cited chunk came from, and may be
    one the caller was denied. `ingest` already records the owning DMC
    (`source_dm`), and `ingest.figure_chunks` already requires it to match; the
    second-look path has to apply the same rule or it can send a different
    package's image to the VLM (red-team P1, 2026-07-27).
    """
    for pkg in package_dirs:
        pkg_dir = Path(pkg)
        for rec in ingest.load_records(pkg_dir):
            if owner_dmc and rec.source_dm != owner_dmc:
                continue
            if rec.icn_id == icn_id and rec.verified:
                try:
                    png = ingest.read_png(ingest.png_path(pkg_dir, icn_id))
                except (ValueError, OSError):
                    return None
                return rec, png
    return None


def figure_second_look(
    question: str,
    figure_chunk: Chunk,
    package_dirs: list[str],
    *,
    budget: Callable[[], bool] | None = None,
) -> dict:
    """Consensus re-read of the figure behind `figure_chunk`. Never raises — a
    `FigureRefusal` is captured as `consensus=False`. Returns a trace dict."""
    icn_id = figure_chunk.icn_refs[0] if figure_chunk.icn_refs else ""
    asset = _load_asset(icn_id, package_dirs, figure_chunk.dmc) if icn_id else None
    if asset is None:
        return {"icn_id": icn_id, "attempted": False, "reason": "figure asset unavailable"}
    rec, png = asset
    try:
        cr = consensus_read(
            png, set(rec.declared_hotspots), rec.part_numbers, question, budget=budget
        )
    except FigureRefusal as exc:
        reason = str(exc)
        return {
            "icn_id": icn_id,
            "attempted": True,
            "consensus": False,
            "reason": reason[:200],
            # Distinguishes "we ran out of demo budget" from "the figure does
            # not support that" — different remediation (round-2 red team).
            "quota_exhausted": reason.startswith(QUOTA_EXHAUSTED),
        }
    return {
        "icn_id": icn_id,
        "attempted": True,
        "consensus": True,
        "agreement": cr.agreement,
        "samples": cr.samples,
        "reading_hotspots": sorted(cr.reading.hotspot_ids()),
    }
