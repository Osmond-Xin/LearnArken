"""Describe-then-index offline pipeline (Day 12, docs/specs/day12.md §3).

Two phases, deliberately split so indexing stays deterministic and cheap:

1. **describe (offline, VLM)** — `describe_dm_figures` renders the committed PNG,
   computes its **SHA-256**, calls the VLM once (with the client's flaky retry),
   runs the **mechanical hotspot diff** (described ids vs the DM-declared
   canonical set, Decision 3a) and the **anchor corroboration** (declared part
   numbers must reappear in the read text, scan T2), and emits a `FigureRecord`.
   A mismatch ⇒ the figure is **degraded** (`verified=False`): recorded, not
   indexed. Records are written next to the asset as `<icn>.describe.json` and
   committed — the VLM description becomes a reviewable, SHA-256-bound artifact.

2. **index (no VLM)** — `figure_chunks` **re-verifies** each committed record
   against the *current* PNG bytes (SHA-256) and the *current* DM-declared
   hotspot set, then turns verified figures into retrievable `Chunk`s
   (chunk_type="figure") whose text is **grounded only in the declared set** —
   VLM free-text (summary/warnings) is kept in the audit record, never indexed
   as authoritative (red-team P1: no unverified VLM text in the corpus).

The SHA-256 binds the description to the exact image bytes and is **enforced at
index time** (a swapped PNG or hand-edited record is skipped, fail closed);
re-running phase 1 and diffing the record is the EVIDENCE.md reproduction
command for figures.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from learnarken.chunking.base import Chunk, make_chunk_id
from learnarken.models import DataModule, HotspotDecl
from learnarken.multimodal.vlm import FigureDescription, describe_figure

logger = logging.getLogger("learnarken")

DESCRIBE_SUFFIX = ".describe.json"
# ICN ids are synthetic and strict-syntax; the regex confines them to the icn/
# dir (red-team P2: an id like `../secret` must never build a path outside it).
ICN_ID_RE = re.compile(r"^ICN-[A-Z0-9][A-Z0-9-]{2,60}$")
MAX_PNG_BYTES = 4_000_000  # cap base64 memory blow-up on a hostile/huge PNG


class FigureRecord(BaseModel):
    """The committed, SHA-256-bound result of describing one figure."""

    model_config = ConfigDict(extra="forbid")  # committed artifact — drift must be visible

    icn_id: str
    source_dm: str  # owning DMC
    png_path: str  # repo-relative path to the canonical PNG
    sha256: str  # of the PNG bytes — the bind key
    declared_hotspots: list[str]  # canonical set from the DM XML (ground truth)
    described_hotspots: list[str]  # what the VLM read (enum-closed)
    part_numbers: list[str]  # declared part numbers (authoritative)
    # Full declared mapping "id|label|part" per hotspot — the exact text that
    # becomes chunk content; bound into the chunk id so an XML label/part edit
    # changes the id and can't hide behind a stale Vespa doc (red-team R2 P1).
    declared_map: list[str]
    summary: str  # VLM summary (descriptive only)
    safety_warnings: list[str]
    hotspots_matched: bool  # described set == declared set (Decision 3a)
    corroborated: bool  # declared part numbers reappear in the read text (scan T2)
    verified: bool  # matched AND corroborated — only these are indexed
    degraded_reason: str = ""  # why an unverified figure was withheld


def sha256_png(png_bytes: bytes) -> str:
    return hashlib.sha256(png_bytes).hexdigest()


def _declared_by_icn(dm: DataModule) -> dict[str, list]:
    by_icn: dict[str, list] = {}
    for h in dm.hotspots:
        by_icn.setdefault(h.icn_ident, []).append(h)
    return by_icn


def _declared_map(decls: list[HotspotDecl]) -> list[str]:
    """The exact declared mapping that becomes chunk text, as sorted
    `id|label|part` strings — the content the chunk id must bind to (R2 P1)."""
    return sorted(f"{h.hotspot_id}|{h.label}|{h.part_number}" for h in decls)


def _map_digest(declared_map: list[str]) -> str:
    return hashlib.sha256("\n".join(declared_map).encode()).hexdigest()[:16]


def png_path(package_dir: Path, icn_id: str) -> Path:
    """Resolve the committed PNG path, confined to `package_dir/icn` (red-team
    P2: a crafted ICN id must not build a path escaping the icn dir)."""
    if not ICN_ID_RE.match(icn_id):
        raise ValueError(f"unsafe ICN id {icn_id!r} (fail closed)")
    icn_dir = (package_dir / "icn").resolve()
    path = (icn_dir / f"{icn_id}.png").resolve()
    if path.parent != icn_dir:
        raise ValueError(f"ICN path {path} escapes {icn_dir} (fail closed)")
    return path


def read_png(path: Path) -> bytes:
    png = path.read_bytes()
    if len(png) > MAX_PNG_BYTES:
        raise ValueError(f"PNG {path.name} is {len(png)} B > {MAX_PNG_BYTES} cap (fail closed)")
    return png


_TOKEN_STRIP = ".,;:()[]\"'"


def _tokenize(texts: list[str]) -> set[str]:
    """Whitespace tokens with surrounding punctuation stripped, so `LA-24-5001-2.`
    matches `LA-24-5001-2` (red-team R2 P3) but `A-1` still won't match `A-10`."""
    tokens: set[str] = set()
    for text in texts:
        for raw in text.replace(",", " ").split():
            tok = raw.strip(_TOKEN_STRIP)
            if tok:
                tokens.add(tok)
    return tokens


def _ocr_tokens(desc: FigureDescription) -> set[str]:
    """Whole-token OCR anchors from the read TEXT only — NOT the model's own
    self-reported `parts` list (red-team P1: the model must not corroborate
    itself)."""
    return _tokenize(desc.reads_text)


def describe_dm_figures(
    dm: DataModule,
    package_dir: Path,
    *,
    describe: Callable[..., FigureDescription] = describe_figure,
    repo_root: Path | None = None,
) -> list[FigureRecord]:
    """Describe every figure of `dm` that carries a declared hotspot set. A
    degraded figure is recorded with `verified=False` (not raised). VLM
    transport/rate-limit failures propagate (VLMError) so the offline run fails
    closed rather than silently emitting an undescribed figure."""
    repo_root = repo_root or Path.cwd()
    records: list[FigureRecord] = []
    for icn_id, decls in _declared_by_icn(dm).items():
        declared = {h.hotspot_id for h in decls}
        part_numbers = sorted({h.part_number for h in decls if h.part_number})
        path = png_path(package_dir, icn_id)
        png = read_png(path)
        rel = path.relative_to(repo_root.resolve()).as_posix()

        desc = describe(png, declared)  # VLMError/VLMRateLimited propagate (fail closed)
        described_ids = desc.hotspot_ids()
        # A refusal (even with evidence) is never a positive read (red-team P1).
        refused = desc.refused
        matched = (not refused) and described_ids == declared
        tokens = _ocr_tokens(desc)
        corroborated = (not refused) and (
            all(pn in tokens for pn in part_numbers) if part_numbers else True
        )
        verified = matched and corroborated
        if refused:
            reason = "vlm refused"
        elif not matched:
            reason = f"hotspot mismatch: declared {sorted(declared)} read {sorted(described_ids)}"
        elif not corroborated:
            reason = f"part numbers {part_numbers} not corroborated in read text"
        else:
            reason = ""

        records.append(
            FigureRecord(
                icn_id=icn_id,
                source_dm=dm.dmc,
                png_path=rel,
                sha256=sha256_png(png),
                declared_hotspots=sorted(declared),
                described_hotspots=sorted(described_ids),
                part_numbers=part_numbers,
                declared_map=_declared_map(decls),
                summary=desc.summary.strip(),
                safety_warnings=[w.strip() for w in desc.safety_warnings],
                hotspots_matched=matched,
                corroborated=corroborated,
                verified=verified,
                degraded_reason=reason[:200],
            )
        )
    return records


def record_path(package_dir: Path, icn_id: str) -> Path:
    return package_dir / "icn" / f"{icn_id}{DESCRIBE_SUFFIX}"


def write_record(package_dir: Path, record: FigureRecord) -> Path:
    path = record_path(package_dir, record.icn_id)
    path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_records(package_dir: Path) -> list[FigureRecord]:
    """Load committed describe records for a package (no VLM)."""
    icn_dir = package_dir / "icn"
    if not icn_dir.is_dir():
        return []
    return [
        FigureRecord.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(icn_dir.glob(f"*{DESCRIBE_SUFFIX}"))
    ]


def format_figure_text(icn_id: str, decls: list[HotspotDecl]) -> str:
    """Retrievable text for a figure chunk, grounded ONLY in the declared set
    (DM XML — authoritative, deterministic, re-verifiable). No VLM free-text is
    indexed (red-team P1)."""
    lines = [f"Figure {icn_id}."]
    for h in sorted(decls, key=lambda d: d.hotspot_id):
        piece = f"Hotspot {h.hotspot_id}"
        if h.label:
            piece += f": {h.label}"
        if h.part_number:
            piece += f" — part {h.part_number}"
        lines.append(piece + ".")
    return "\n".join(lines)


def figure_chunks(
    dm: DataModule,
    records: list[FigureRecord],
    strategy: str,
    package_dir: Path,
    *,
    repo_root: Path | None = None,
) -> list[Chunk]:
    """Build retrievable figure chunks for a DM from its verified records,
    **re-verifying** each against the current assets at index time (red-team P1):
    the committed record's SHA-256 must still match the on-disk PNG, and its
    hotspot set must still match the DM XML. Any drift ⇒ the figure is skipped
    (fail closed), so a swapped PNG or hand-edited record cannot be indexed.
    Degraded (unverified) figures are withheld (Decision 3a)."""
    repo_root = repo_root or Path.cwd()
    by_icn = _declared_by_icn(dm)
    chunks: list[Chunk] = []
    for rec in records:
        if rec.source_dm != dm.dmc or not rec.verified:
            continue
        decls = by_icn.get(rec.icn_id)
        if not decls:  # record for a figure no longer declared on this DM
            logger.warning("figure %s: no declared hotspots on %s — skipping", rec.icn_id, dm.dmc)
            continue
        current_declared = sorted({h.hotspot_id for h in decls})
        current_map = _declared_map(decls)
        try:
            png = read_png(png_path(package_dir, rec.icn_id))
        except (ValueError, OSError) as exc:
            logger.warning(
                "figure %s: PNG unreadable (%s) — skipping (fail closed)", rec.icn_id, exc
            )
            continue
        if sha256_png(png) != rec.sha256:
            logger.warning("figure %s: PNG sha != record sha — skipping (fail closed)", rec.icn_id)
            continue
        # Re-verify BOTH the hotspot-id set AND the full declared mapping (labels
        # + part numbers), so an XML label/part edit is caught, not just an id
        # change (red-team R2 P1).
        if (
            current_declared != rec.declared_hotspots
            or current_declared != rec.described_hotspots
            or current_map != rec.declared_map
        ):
            logger.warning(
                "figure %s: declared/described drift — skipping (fail closed)", rec.icn_id
            )
            continue
        source_path = f"figure/{rec.icn_id}"
        chunks.append(
            Chunk(
                # chunk id binds BOTH the image bytes and the declared mapping,
                # so any edit to a label/part number mints a new id (R2 P1): a
                # stale Vespa doc then fails corpus verification instead of
                # silently serving old text.
                chunk_id=make_chunk_id(
                    dm.dmc, source_path, strategy, f"{rec.sha256[:8]}{_map_digest(current_map)[:8]}"
                ),
                strategy=strategy,
                dmc=dm.dmc,
                dm_title=dm.title,
                issue_info=dm.issue_info.as_str() if dm.issue_info else "",
                chunk_type="figure",
                source_path=source_path,
                text=format_figure_text(rec.icn_id, decls),
                applicability=dm.applicability,
                security_classification=dm.security_classification,
                effective_date=dm.extension.effective_date if dm.extension else None,
                expiry_date=dm.extension.expiry_date if dm.extension else None,
                icn_refs=[rec.icn_id],
            )
        )
    return chunks
