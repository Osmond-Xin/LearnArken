"""Multiprocessing shard adapter for package validation (Day 13, Decision 1).

Shards are **per-DM-file** (not "replicate N packages" — that would manufacture
fake I/O/memory load, Decision 1). Each worker validates its files (L0/L1/L2) and
returns picklable `FileResult`s; the main process merges them and runs L3 — which
needs whole-package state and is therefore the serial fraction (Amdahl). The
result is **byte-equivalent to the single-process baseline** (`analyze_package`);
both share `_process_file` + `_merge_file_results`, and the benchmark/tests assert
equality.
"""

from __future__ import annotations

from pathlib import Path

from learnarken.models import PackageModel
from learnarken.perf.shard import make_shards, run_sharded
from learnarken.validation.engine import (
    DEFAULT_ACCEPTED_MODELS,
    FileResult,
    _merge_file_results,
    _process_file,
    build_schema,
    list_package_files,
)
from learnarken.validation.report import ValidationReport


def _validate_shard(paths: list[str]) -> list[FileResult]:
    """Worker: validate a shard of files. Builds **one** schema for the whole
    shard (per-process; lxml XMLSchema is not safe to share, so never passed in)
    and reads its own files from the given paths — "pass the shard description,
    not the data" (INV-2 / DR B). Module-level so it is picklable under spawn.
    `accepted_models` is not needed here — it only feeds L3 in the merge."""
    schema = build_schema()
    try:
        return [_process_file(Path(p), schema) for p in paths]
    except Exception as exc:  # noqa: BLE001 — add shard context before it crosses
        # the pool boundary, where the default error is context-free (red-team P3).
        raise RuntimeError(f"validation shard failed (files={paths}): {exc}") from exc


def analyze_package_sharded(
    package_dir: str | Path,
    accepted_models: tuple[str, ...] = DEFAULT_ACCEPTED_MODELS,
    *,
    workers: int,
) -> tuple[ValidationReport, PackageModel]:
    """Validate a package with per-DM-file multiprocessing sharding.

    `workers` requested; effective parallelism is capped by the file count
    (a small corpus cannot use all workers — Decision 1c). Equivalent to
    `analyze_package` (Decision 1b).
    """
    directory = Path(package_dir)
    files = list_package_files(directory)
    shards = make_shards([str(p) for p in files], workers)
    results_list = run_sharded(shards, _validate_shard, workers=workers)
    results = {result.file: result for result in results_list}
    return _merge_file_results(directory, files, results, accepted_models)
