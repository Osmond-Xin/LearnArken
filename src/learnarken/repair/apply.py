"""Approve-then-write commit for repair patches (Day 7, Ruling 1 / §1.3).

Apply is never silent: `run_repair` prompts the human per apply-eligible patch;
only approved edits reach this module. Before touching the active package the
combined approved edit set is re-verified — applied to a full temp copy and
validated — and refused (fail closed) if it introduces any new finding. The
active files are then swapped atomically with a `.bak` kept for rollback, and
`recover_interrupted_apply` restores — from a journal this process wrote — any
file a crash left mid-swap (INV-2: idempotent, visible, rollback-able writes).

Hardened after the Day 7 red-team: filenames are jailed to known top-level
package modules (#6), the active file is re-checked against the bytes the
preview validated just before each swap (TOCTOU, #10), and recovery trusts only
journalled backups (#11).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from learnarken.repair.models import EditOp, ValidatorDelta
from learnarken.repair.patch import apply_edits
from learnarken.repair.sandbox import _safe_basename
from learnarken.repair.tools import finding_key
from learnarken.validation import DEFAULT_ACCEPTED_MODELS, analyze_package

_BAK = ".bak"
_NEW = ".new"
_JOURNAL = ".repair-apply.journal"


class ApplyRefused(RuntimeError):
    """The approved edit set would introduce new findings — not written (fail closed)."""


@dataclass
class ApplyResult:
    written: list[str]
    delta: ValidatorDelta


def _baseline_keys(package_dir: Path, accepted_models: tuple[str, ...]) -> set[str]:
    report, _ = analyze_package(package_dir, accepted_models)
    return {finding_key(f) for f in report.findings}


def _validated_targets(src: Path, edits_by_file: dict[str, list[EditOp]]) -> dict[str, bytes]:
    """Jail each filename to a real, non-symlink, top-level package module (#6)."""
    originals: dict[str, bytes] = {}
    for name in edits_by_file:
        _safe_basename(name)
        target = src / name
        if not target.is_file() or target.is_symlink():
            raise ApplyRefused(f"unknown or unsafe target file: {name!r}")
        originals[name] = target.read_bytes()
    return originals


def verify_and_apply(
    package_dir: str | Path,
    edits_by_file: dict[str, list[EditOp]],
    accepted_models: tuple[str, ...] = DEFAULT_ACCEPTED_MODELS,
) -> ApplyResult:
    """Verify the combined approved edits, then atomically swap them into active."""
    src = Path(package_dir)
    if not edits_by_file:
        return ApplyResult(written=[], delta=ValidatorDelta(findings_before=0, findings_after=0))

    originals = _validated_targets(src, edits_by_file)
    edited = {name: apply_edits(originals[name], edits) for name, edits in edits_by_file.items()}
    before = _baseline_keys(src, accepted_models)

    # Re-verify the whole package as it *would* look after the swap: a full temp
    # copy with the edits overlaid. The active dir is not touched until this passes.
    with tempfile.TemporaryDirectory(prefix="learnarken-apply-") as tmp:
        preview = Path(tmp)
        for xml in src.glob("*.xml"):
            if not xml.is_symlink():
                shutil.copy2(xml, preview / xml.name)
        if (src / "icn").is_dir():
            shutil.copytree(src / "icn", preview / "icn", symlinks=False)
        for name, content in edited.items():
            (preview / name).write_bytes(content)
        after = _baseline_keys(preview, accepted_models)

    introduced = sorted(after - before)
    if introduced:
        raise ApplyRefused(
            f"approved edits would introduce {len(introduced)} new finding(s): {introduced[:3]} "
            "— refusing to write (fail closed)"
        )

    written = _atomic_swap(src, edited, originals)
    return ApplyResult(
        written=written,
        delta=ValidatorDelta(
            findings_before=len(before),
            findings_after=len(after),
            cleared=sorted(before - after),
            introduced=[],
        ),
    )


def _atomic_swap(src: Path, edited: dict[str, bytes], originals: dict[str, bytes]) -> list[str]:
    """Swap each edited file into place atomically, keeping a .bak for rollback.

    A journal names the files this process is swapping, so recovery restores
    only our backups (#11). Just before each swap the active file is re-checked
    against the bytes the preview validated — a concurrent change aborts the
    whole apply, fail closed (TOCTOU, #10). On any failure the already-swapped
    files are rolled back from their .bak.
    """
    journal = src / _JOURNAL
    journal.write_text("\n".join(edited), encoding="utf-8")
    done: list[str] = []
    try:
        for name, content in edited.items():
            active = src / name
            if active.read_bytes() != originals[name]:
                raise OSError(f"active file {name!r} changed under apply — aborting (fail closed)")
            shutil.copy2(active, src / (name + _BAK))
            tmp = src / (name + _NEW)
            tmp.write_bytes(content)
            os.replace(tmp, active)  # atomic on POSIX
            done.append(name)
    except OSError:
        for name in done:  # rollback the ones already swapped
            bak = src / (name + _BAK)
            if bak.is_file():
                os.replace(bak, src / name)
        for name in edited:  # clean any leftover .new
            (src / (name + _NEW)).unlink(missing_ok=True)
        journal.unlink(missing_ok=True)
        raise
    for name in done:  # commit: drop the backups
        (src / (name + _BAK)).unlink(missing_ok=True)
    journal.unlink(missing_ok=True)
    return done


def recover_interrupted_apply(package_dir: str | Path) -> list[str]:
    """Restore files a crash left mid-swap, using this project's apply journal.

    Only backups named in the journal (written by `_atomic_swap` before it began)
    are trusted — a stray `.bak` dropped by anything else is ignored (#11).
    """
    src = Path(package_dir)
    journal = src / _JOURNAL
    if not journal.is_file():
        return []
    restored: list[str] = []
    for name in journal.read_text(encoding="utf-8").split():
        _safe_basename(name)
        bak = src / (name + _BAK)
        if bak.is_file() and not bak.is_symlink():
            os.replace(bak, src / name)
            restored.append(name)
        (src / (name + _NEW)).unlink(missing_ok=True)
    journal.unlink(missing_ok=True)
    return restored
