"""Day 12 multimodal answer-level eval (docs/specs/day12.md, INV-7 honesty).

Runs the answer engine over the three-class golden set and scores per class:

- **answer_in_figure** — pass = answered (not refused), the expected part/number
  appears, and (when given) the `[ICN-…, Hotspot NN]` citation is emitted;
- **no_answer_figure** — pass = refused (G15 `figure-out-of-description`);
- **conflict** — pass = the answer does NOT force one side (refuses, or presents
  BOTH conflicting part numbers).

Scores are reported **k/n, not percentages** (n<3 per class → indicative, Day 4
precedent). The generator is non-deterministic (LLM); this is a single frozen
pass (Day 8 discipline — repeat with `--repeat` to inspect stability). Needs
services (Vespa + LLM). Output: `eval/results/day12-multimodal.json`.

    uv run python tools/day12_eval.py [--repeat 1]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from learnarken.answer.engine import answer_question

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "eval" / "golden" / "day12-multimodal.jsonl"
OUT = REPO / "eval" / "results" / "day12-multimodal.json"
PKGS = [str(REPO / "samples" / "package-a"), str(REPO / "samples" / "package-c")]


def _load() -> list[dict]:
    items = []
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            items.append(json.loads(line))
    return items


def _passed(item: dict, result) -> bool:
    exp = item["expect"]
    if exp == "refuse":
        return bool(result.refused)
    if exp == "present_both_or_refuse":
        if result.refused:
            return True
        text = result.answer_text.lower()
        return all(p.lower() in text for p in item["conflict_parts"])
    # answer_in_figure
    if result.refused:
        return False
    text = result.answer_text.lower()
    contains = [c.lower() for c in item.get("answer_contains", [])]
    hit = any(c in text for c in contains) if item.get("answer_contains_any") else all(
        c in text for c in contains
    )
    if item.get("figure_ref"):
        hit = hit and any(c.figure_ref == item["figure_ref"] for c in result.citations)
    return hit


def _run_pass(items: list[dict]) -> dict:
    by_class: dict[str, list[bool]] = {}
    detail = []
    for item in items:
        result = answer_question(item["query"], package_dirs=PKGS, mode="hybrid-rerank")
        ok = _passed(item, result)
        by_class.setdefault(item["category"], []).append(ok)
        detail.append(
            {
                "query_id": item["query_id"],
                "category": item["category"],
                "passed": ok,
                "refused": result.refused,
                "gate": result.refusal_gate,
            }
        )
    scores = {c: {"k": sum(v), "n": len(v)} for c, v in by_class.items()}
    return {"scores": scores, "detail": detail}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()
    items = _load()
    runs = [_run_pass(items) for _ in range(args.repeat)]
    result = {
        "note": (
            "answer-level three-class eval; k/n not %, n<3 indicative (INV-7). "
            "Non-deterministic generator (LLM); synthetic figures do not extrapolate "
            "to real scans."
        ),
        "golden": str(GOLDEN.relative_to(REPO)),
        "packages": [str(Path(p).relative_to(REPO)) for p in PKGS],
        "repeat": args.repeat,
        "runs": runs,
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for cls, s in runs[0]["scores"].items():
        tag = " (indicative)" if s["n"] < 3 else ""
        print(f"{cls}: {s['k']}/{s['n']}{tag}")
    print(f"→ {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
