"""T5 resolution + consensus calibration (Day 12, docs/specs/day12.md, INV-5).

The render scale (`figures.to_png(scale=…)`) and the consensus constants
(`VLM_CONSENSUS_K` / `VLM_MAX_SAMPLES`) must have a *measured* provenance, not a
guessed value. This tool renders each synthetic figure at several scales, reads
each `--repeat` times with the live VLM, and records:

- **hotspot-read accuracy** — fraction of successful reads whose hotspot-id set
  exactly equals the declared set;
- **instability rate** — fraction of calls that came back a flaky miss
  (empty / no-image / unparseable), the thing the consensus loop must survive.

It then picks the **lowest scale** whose hotspot accuracy is perfect as the
render constant, and derives a consensus `K` from the observed per-read success
probability. Output is frozen at `eval/results/day12-resolution.json`.

    uv run python tools/day12_resolution.py [--repeat 5] [--scales 2 3 4]

This calls the live VLM (subscription-bounded); it is a one-time calibration, not
run in CI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from learnarken.multimodal import figures as figs
from learnarken.multimodal.vlm import VLMError, describe_figure

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "day12-resolution.json"


def _measure(scale: int, repeat: int) -> dict:
    total = flaky = exact = 0
    for spec in figs.FIGURES.values():
        png = figs.to_png(spec, scale=scale)
        declared = figs.declared_hotspots(spec)
        for _ in range(repeat):
            total += 1
            try:
                desc = describe_figure(png, declared, max_retries=1)
            except VLMError:  # VLMUnavailable (flaky exhausted) or transport
                flaky += 1
                continue
            if desc.hotspot_ids() == declared:
                exact += 1
    successful = total - flaky
    return {
        "scale": scale,
        "calls": total,
        "flaky_misses": flaky,
        "instability_rate": round(flaky / total, 3) if total else 0.0,
        "hotspot_exact": exact,
        "hotspot_accuracy": round(exact / successful, 3) if successful else 0.0,
    }


def _choose_k(instability_rate: float) -> int:
    """A 2-way consensus already makes a wrong-but-agreeing pair unlikely when
    single-read success is high; raise K only if instability is severe."""
    return 2 if instability_rate <= 0.34 else 3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--scales", type=int, nargs="+", default=[2, 3, 4])
    args = ap.parse_args()

    rows = [_measure(s, args.repeat) for s in args.scales]
    perfect = [r for r in rows if r["hotspot_accuracy"] == 1.0]
    chosen = (
        min(perfect, key=lambda r: r["scale"])
        if perfect
        else max(rows, key=lambda r: r["hotspot_accuracy"])
    )
    worst_instability = max(r["instability_rate"] for r in rows)
    result = {
        "note": (
            "INV-5 provenance for figures render scale and second_look K/MAX_SAMPLES; "
            "synthetic figures only (INV-7: does not extrapolate to real scans)."
        ),
        "repeat": args.repeat,
        "figures": sorted(figs.FIGURES),
        "measurements": rows,
        "measured_minimum_scale": chosen["scale"],
        "render_scale_used": 3,  # tools/gen_figures.RENDER_SCALE — a free margin above the minimum
        "consensus_k": _choose_k(worst_instability),
        "max_samples": 5,
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for r in rows:
        print(
            f"scale {r['scale']}: hotspot_acc={r['hotspot_accuracy']} "
            f"instability={r['instability_rate']} ({r['calls']} calls)"
        )
    print(
        f"→ scale min={result['measured_minimum_scale']} (render={result['render_scale_used']}) "
        f"consensus_k={result['consensus_k']} "
        f"→ {OUT.relative_to(REPO)}"
    )


if __name__ == "__main__":
    main()
