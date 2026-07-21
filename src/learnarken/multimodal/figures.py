"""Declarative synthetic ICN figures (Day 12, docs/specs/day12.md, Interfaces §2).

A single `FigureSpec` is the **source of truth** for each synthetic ICN. From it
we emit BOTH:

- an **SVG** — the S1000D graphic artifact the DM references via
  `<graphic infoEntityIdent="ICN-…"/>`, and the source of the `<text>` white-list
  anchor (scan T2);
- a **PNG** (via Pillow) — the raster the VLM reads, committed and SHA-256-bound.

One source ⇒ no SVG↔PNG divergence. Pillow is deterministic within an environment
(bundled font, no system fonts); cross-environment byte-identity is not promised
— the committed PNG is canonical (scan T3, the honest position). Everything is
synthetic (INV-1): no real S1000D graphics are ever read or copied.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

# Canvas base units (SVG viewBox); the PNG is rendered at base * scale.
_W, _H = 320, 200
_HOTSPOT_R = 11  # marker radius in base units


@dataclass(frozen=True)
class Shape:
    """One drawn primitive. kind ∈ {rect, line, circle}; coords in base units."""

    kind: str
    coords: tuple[int, ...]
    fill: str = "none"


@dataclass(frozen=True)
class HotspotSpec:
    id: str  # e.g. "01" — cited as "Hotspot 01"
    label: str  # what the callout points at
    part_number: str  # e.g. "LA-29-4711-9"
    x: int  # marker centre, base units
    y: int


@dataclass(frozen=True)
class FigureSpec:
    icn_id: str
    title: str  # ASCII only (scan T3)
    shapes: tuple[Shape, ...]
    hotspots: tuple[HotspotSpec, ...]
    safety_warnings: tuple[str, ...] = ()


def declared_hotspots(spec: FigureSpec) -> set[str]:
    """The canonical hotspot-id set the VLM description is diffed against."""
    return {h.id for h in spec.hotspots}


def text_whitelist(spec: FigureSpec) -> set[str]:
    """ASCII tokens drawn into the figure that the VLM should read back
    verbatim — the deterministic corroboration anchor (scan T2)."""
    tokens = {h.id for h in spec.hotspots} | {h.part_number for h in spec.hotspots}
    return {t for t in tokens if t}


def to_svg(spec: FigureSpec) -> str:
    """Render the spec to an SVG string (the DM-referenced ICN artifact)."""
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}" '
        f'width="{_W}" height="{_H}">',
        f"  <!-- Synthetic LearnArken ICN (INV-1): {spec.icn_id}. Generated from "
        "multimodal/figures.py; do not hand-edit. -->",
        f'  <rect x="1" y="1" width="{_W - 2}" height="{_H - 2}" fill="none" '
        'stroke="#666" stroke-width="2"/>',
    ]
    for s in spec.shapes:
        if s.kind == "rect":
            x, y, w, h = s.coords
            parts.append(
                f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" '
                f'fill="{s.fill}" stroke="#345" stroke-width="2"/>'
            )
        elif s.kind == "line":
            x1, y1, x2, y2 = s.coords
            parts.append(
                f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#345" stroke-width="3"/>'
            )
        elif s.kind == "circle":
            cx, cy, r = s.coords
            parts.append(
                f'  <circle cx="{cx}" cy="{cy}" r="{r}" fill="{s.fill}" '
                'stroke="#345" stroke-width="2"/>'
            )
    for h in spec.hotspots:
        parts.append(
            f'  <circle cx="{h.x}" cy="{h.y}" r="{_HOTSPOT_R}" fill="#fff" '
            'stroke="#b00" stroke-width="2"/>'
        )
        parts.append(
            f'  <text x="{h.x}" y="{h.y + 4}" font-family="monospace" '
            f'font-size="12" text-anchor="middle" fill="#b00">{h.id}</text>'
        )
        parts.append(
            f'  <text x="{h.x}" y="{h.y + _HOTSPOT_R + 12}" font-family="monospace" '
            f'font-size="9" text-anchor="middle" fill="#333">{h.part_number}</text>'
        )
    for i, warn in enumerate(spec.safety_warnings):
        parts.append(
            f'  <text x="8" y="{16 + i * 12}" font-family="monospace" font-size="9" '
            f'fill="#b00">WARNING: {warn}</text>'
        )
    parts.append(
        f'  <text x="{_W // 2}" y="{_H - 8}" font-family="monospace" font-size="11" '
        f'text-anchor="middle" fill="#333">{spec.title}</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow without the size kwarg
        return ImageFont.load_default()


def to_png(spec: FigureSpec, *, scale: int = 3) -> bytes:
    """Render the spec to PNG bytes via Pillow (the VLM raster). `scale` is the
    resolution knob (Decision 4 constant); text is drawn large enough to read."""
    img = Image.new("RGB", (_W * scale, _H * scale), (255, 255, 255))
    d = ImageDraw.Draw(img)

    def sc(*vals: int) -> tuple[int, ...]:
        return tuple(v * scale for v in vals)

    d.rectangle(sc(1, 1, _W - 1, _H - 1), outline=(102, 102, 102), width=2)
    for s in spec.shapes:
        if s.kind == "rect":
            x, y, w, h = s.coords
            d.rectangle(sc(x, y, x + w, y + h), outline=(51, 68, 85), width=2)
        elif s.kind == "line":
            d.line(sc(*s.coords), fill=(51, 68, 85), width=3)
        elif s.kind == "circle":
            cx, cy, r = s.coords
            d.ellipse(sc(cx - r, cy - r, cx + r, cy + r), outline=(51, 68, 85), width=2)

    id_font = _font(int(_HOTSPOT_R * scale * 1.1))
    part_font = _font(int(9 * scale))
    title_font = _font(int(11 * scale))
    red, ink, white = (187, 0, 0), (51, 51, 51), (255, 255, 255)
    for h in spec.hotspots:
        r = _HOTSPOT_R
        d.ellipse(sc(h.x - r, h.y - r, h.x + r, h.y + r), fill=white, outline=red, width=2)
        d.text(sc(h.x, h.y), h.id, fill=red, font=id_font, anchor="mm")
        d.text(sc(h.x, h.y + r + 8), h.part_number, fill=ink, font=part_font, anchor="mm")
    warn_font = _font(int(9 * scale))
    for i, warn in enumerate(spec.safety_warnings):
        d.text(sc(8, 12 + i * 12), f"WARNING: {warn}", fill=red, font=warn_font, anchor="lm")
    d.text(sc(_W // 2, _H - 8), spec.title, fill=(51, 51, 51), font=title_font, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# --- The synthetic figure catalogue (2 ICNs; ≤3 to protect the 43-chunk pool) ---

FIGURES: dict[str, FigureSpec] = {
    # Upgraded in place: the existing ICN wired to DMC-LA100-A-29-10-00-00A-941A-D.
    "ICN-LA100-29-001-01": FigureSpec(
        icn_id="ICN-LA100-29-001-01",
        title="LA100 hydraulic pump (synthetic)",
        shapes=(
            Shape("rect", (90, 60, 140, 80), fill="#d8e4f0"),
            Shape("circle", (160, 100, 24), fill="#f0f0f0"),
            Shape("line", (30, 100, 90, 100)),
            Shape("line", (230, 100, 290, 100)),
        ),
        hotspots=(
            HotspotSpec("01", "inlet port", "LA-29-4711-1", 52, 100),
            HotspotSpec("02", "pump body", "LA-29-4711-9", 160, 62),
            HotspotSpec("03", "outlet port", "LA-29-0025-4", 268, 100),
        ),
        safety_warnings=("Depressurise the system before removing the pump.",),
    ),
    # New: attached to the Main battery remove-procedures DM in package-c
    # (DMC-LA100-A-24-50-00-00A-520A-A). Part numbers are synthetic (INV-1).
    "ICN-LA100-24-002-01": FigureSpec(
        icn_id="ICN-LA100-24-002-01",
        title="LA100 main battery (synthetic)",
        shapes=(
            Shape("rect", (110, 70, 100, 60), fill="#e6f0e6"),
            Shape("line", (40, 90, 110, 90)),
            Shape("line", (210, 90, 280, 90)),
            Shape("circle", (135, 70, 6), fill="#f0f0f0"),
        ),
        hotspots=(
            HotspotSpec("01", "positive terminal", "LA-24-5001-2", 135, 62),
            HotspotSpec("02", "battery housing", "LA-24-5002-6", 160, 128),
        ),
        safety_warnings=("Battery acid is corrosive. Wear eye protection.",),
    ),
}
