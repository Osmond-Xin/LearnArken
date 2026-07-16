"""Chunking entry point (Day 3, docs/specs/day3.md).

`chunk_package` walks a package's data modules and produces retrieval chunks
under the chosen strategy. It reuses the Day 2 loader for parsing and the
canonical model for metadata, so chunks inherit applicability, hazard flags,
and graph hooks without re-deriving them.
"""

from __future__ import annotations

import logging
from pathlib import Path

from learnarken.chunking import recursive, semantic, structure
from learnarken.chunking.base import Chunk, applies_to, make_chunk_id
from learnarken.loader import MAX_FILE_BYTES, load_data_module, parse_file
from learnarken.package import NotAPackageError

logger = logging.getLogger("learnarken")

STRATEGIES = {
    structure.STRATEGY: structure.chunk_dm,
    recursive.STRATEGY: recursive.chunk_dm,
    semantic.STRATEGY: semantic.chunk_dm,  # Day 4a (spec Q5); makes network calls
}

__all__ = [
    "Chunk",
    "applies_to",
    "make_chunk_id",
    "chunk_package",
    "STRATEGIES",
    "PartialPackageError",
]


class PartialPackageError(Exception):
    """One or more DMs could not be parsed/modeled — refused, fail closed (INV-4).

    Chunking a package with unreadable modules would silently drop content
    (a missing safety DM vanishes from the index). By default this is an error;
    callers that genuinely want a best-effort index pass `skip_bad=True`.
    """

    def __init__(self, failures: list[tuple[str, str]]) -> None:
        self.failures = failures
        listing = "; ".join(f"{name}: {err}" for name, err in failures)
        super().__init__(f"{len(failures)} data module(s) could not be chunked — {listing}")


def chunk_package(
    package_dir: str | Path, strategy: str = "structure", skip_bad: bool = False
) -> list[Chunk]:
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
    failures: list[tuple[str, str]] = []
    for path in dm_files:
        # Enforce the fail-closed size cap on the chunk path too (the validate
        # path already does — red-team R4): never read an oversized file fully.
        if path.stat().st_size > MAX_FILE_BYTES:
            logger.warning("chunk_package: %s exceeds the %d-byte cap", path.name, MAX_FILE_BYTES)
            failures.append((path.name, f"exceeds {MAX_FILE_BYTES}-byte size cap"))
            continue
        try:
            tree, digest = parse_file(path)
            dm = load_data_module(path, tree.getroot())
        except Exception as exc:  # noqa: BLE001 — collect, then fail closed below
            logger.warning("chunk_package: %s could not be chunked (%s)", path.name, exc)
            failures.append((path.name, str(exc)))
            continue
        chunks.extend(chunk_dm(path, tree, dm, digest))
    # Fail closed (INV-4): a package with unreadable modules is refused unless the
    # caller explicitly opts into a partial index.
    if failures and not skip_bad:
        raise PartialPackageError(failures)
    return chunks
