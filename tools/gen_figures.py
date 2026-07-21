"""Regenerate the synthetic ICN assets (Day 12, docs/specs/day12.md).

Writes each `FIGURES` spec to its package `icn/` dir as BOTH an `.svg` (the
DM-referenced S1000D artifact) and a `.png` (the VLM raster, committed and
SHA-256-bound). The committed PNG is the canonical byte source for the ingest
checksum (scan T3). Run after editing `multimodal/figures.py`:

    uv run python tools/gen_figures.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from learnarken.multimodal import figures as F

REPO = Path(__file__).resolve().parents[1]

# icn_id → package dir holding its DM + icn/ folder.
PLACEMENT = {
    "ICN-LA100-29-001-01": REPO / "samples" / "package-a",
    "ICN-LA100-24-002-01": REPO / "samples" / "package-c",
}
RENDER_SCALE = 3  # Decision 4 constant; see eval/results/day12-resolution.json


def main() -> None:
    for icn_id, spec in F.FIGURES.items():
        pkg = PLACEMENT[icn_id]
        icn_dir = pkg / "icn"
        icn_dir.mkdir(parents=True, exist_ok=True)
        svg_path = icn_dir / f"{icn_id}.svg"
        png_path = icn_dir / f"{icn_id}.png"
        svg_path.write_text(F.to_svg(spec), encoding="utf-8")
        png = F.to_png(spec, scale=RENDER_SCALE)
        png_path.write_bytes(png)
        print(f"{icn_id}: {svg_path.relative_to(REPO)} + {png_path.relative_to(REPO)} "
              f"({len(png)} B, sha256 {hashlib.sha256(png).hexdigest()[:16]})")


if __name__ == "__main__":
    main()
