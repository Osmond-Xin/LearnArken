"""Chunking entry point (Day 3, docs/specs/day3.md).

`chunk_package` walks a package's data modules and produces retrieval chunks
under the chosen strategy. It reuses the Day 2 loader for parsing and the
canonical model for metadata, so chunks inherit applicability, hazard flags,
and graph hooks without re-deriving them.
"""

from __future__ import annotations

import logging
from pathlib import Path

from learnarken.chunking import recursive, structure
from learnarken.chunking.base import Chunk, applies_to, make_chunk_id
from learnarken.loader import load_data_module, parse_file
from learnarken.package import NotAPackageError

logger = logging.getLogger("learnarken")

STRATEGIES = {structure.STRATEGY: structure.chunk_dm, recursive.STRATEGY: recursive.chunk_dm}

__all__ = ["Chunk", "applies_to", "make_chunk_id", "chunk_package", "STRATEGIES"]


def chunk_package(package_dir: str | Path, strategy: str = "structure") -> list[Chunk]:
    package_dir = Path(package_dir)
    if not package_dir.is_dir():
        raise NotAPackageError(f"not a directory: {package_dir}")
    dm_files = sorted(package_dir.glob("DMC-*.xml"))
    if not dm_files:
        raise NotAPackageError(f"no data modules (DMC-*.xml) to chunk in: {package_dir}")
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; choose from {sorted(STRATEGIES)}")
    chunk_dm = STRATEGIES[strategy]

    chunks: list[Chunk] = []
    for path in dm_files:
        try:
            tree = parse_file(path)[0]
            dm = load_data_module(path, tree.getroot())
        except Exception as exc:  # noqa: BLE001 — never index a partially-parsed DM
            logger.warning("chunk_package: skipping unparseable %s (%s)", path.name, exc)
            continue
        chunks.extend(chunk_dm(path, tree, dm))
    return chunks
