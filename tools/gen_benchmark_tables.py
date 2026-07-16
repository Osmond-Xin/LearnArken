"""Generate the README benchmark tables from eval artifacts — never hand-edit.

Born from red-team day4 #1: a hand-edited README row was arithmetically
impossible (R@5 > R@10). Extended for #16: the tables are rewritten *in place*
between `<!-- BEGIN gen:... -->` markers, so drift between artifacts and
published tables is structurally impossible. The script refuses to emit any
row that violates Recall monotonicity.

    uv run learnarken eval ablation --json > eval/results/day4-ablation.json
    uv run python tools/dense_bakeoff.py        # also writes day4-bakeoff.json
    uv run python tools/gen_benchmark_tables.py # rewrites README blocks
"""

from __future__ import annotations

import json
from pathlib import Path

ABLATION = Path("eval/results/day4-ablation.json")
BAKEOFF = Path("eval/results/day4-bakeoff.json")
README = Path("README.md")

MODE_LABELS = {
    "bm25": "bm25 (in-process)",
    "dense": "dense (Vespa + Qwen3-8B)",
    "hybrid": "hybrid (RRF)",
    "hybrid-rerank": "hybrid + rerank",
}

PROVIDER_LABELS = {
    "bge-m3": "BGE-M3 (local)",
    "qwen3-8b": "Qwen3-Embedding-8B (local)",
}

# Historical row (client removed by the Day 4 adjudication): reproducible only
# at commit b414fa4. Kept here — with provenance — rather than hand-edited in
# the README, so the generator owns every published cell.
MINIMAX_ROW = "| MiniMax embo-01 (remote) † | 0.50 | 0.68 | 0.36 | 0.43 |"

INDICATIVE_N = 3  # per-category cells under this n are rendered in italics


def _check_monotonic(rows: dict[str, dict], source: Path) -> None:
    for name, r in rows.items():
        if r["recall@5"] > r["recall@10"] + 1e-9:
            raise SystemExit(
                f"REFUSING to emit table: {name} in {source} has Recall@5 "
                f"{r['recall@5']} > Recall@10 {r['recall@10']} — impossible row "
                "(red-team day4 #1)"
            )


def _short_revisions(revisions: dict[str, str]) -> str:
    return ", ".join(f"`{name} @ {sha[:9]}`" for name, sha in sorted(revisions.items()))


def render_ablation(report: dict) -> list[str]:
    results = report["results"]
    _check_monotonic(results, ABLATION)
    n_eval = {r["n_evaluated"] for r in results.values()}
    n_na = {r["n_no_answer"] for r in results.values()}
    assert len(n_eval) == 1 and len(n_na) == 1, "modes evaluated different query sets"

    lines = [
        f"Ranking metrics over **answerable n={n_eval.pop()}**; zero-hit rate over "
        f"the **{n_na.pop()} no-answer traps** (red-team day4 #2 labeling).",
        "",
        "| Mode | Recall@5 | Recall@10 | MRR | nDCG@10 | Zero-hit rate | p50 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    best = {
        k: max(r[k] for r in results.values())
        for k in ("recall@5", "recall@10", "mrr", "ndcg@10")
    }
    for mode, r in results.items():
        cells = []
        for key in ("recall@5", "recall@10", "mrr", "ndcg@10"):
            value = f"{r[key]:.2f}"
            cells.append(f"**{value}**" if abs(r[key] - best[key]) < 1e-9 else value)
        p50 = report["p50_ms"][mode]
        p50_text = "<1 ms" if p50 < 1 else f"{p50:.0f} ms"
        zero_hit = f"{r['zero_hit_rate']:.2f}"
        if mode == "bm25":
            zero_hit = f"**{zero_hit}**"
        label = MODE_LABELS.get(mode, mode)
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {zero_hit} | {p50_text} |")

    per_cat = report.get("per_category_recall")
    if per_cat:
        cat_n = report.get("per_category_n", {})
        cats = sorted(next(iter(per_cat.values())))
        lines += [
            "",
            "Per-category Recall@5 (answerable queries only; *italic* cells have "
            f"n<{INDICATIVE_N} and are indicative):",
            "",
            "| Mode | "
            + " | ".join(f"{c.replace('_', '-')} (n={cat_n.get(c, '?')})" for c in cats)
            + " |",
            "| --- |" + " --- |" * len(cats),
        ]
        for mode, by_cat in per_cat.items():
            cells = []
            for c in cats:
                value = f"{by_cat[c]:.2f}"
                if isinstance(cat_n.get(c), int) and cat_n[c] < INDICATIVE_N:
                    value = f"*{value}*"
                cells.append(value)
            lines.append(f"| {mode} | " + " | ".join(cells) + " |")

    revisions = report.get("model_revisions")
    if revisions:
        lines += ["", f"Model snapshots pinned (INV-5): {_short_revisions(revisions)}."]
    return lines


def render_bakeoff(report: dict) -> list[str]:
    results = {name: r["overall"] for name, r in report["results"].items()}
    _check_monotonic(results, BAKEOFF)
    lines = [
        "| Provider | Recall@5 | Recall@10 | MRR | nDCG@10 |",
        "| --- | --- | --- | --- | --- |",
        MINIMAX_ROW,
    ]
    best = {
        k: max(r[k] for r in results.values())
        for k in ("recall@5", "recall@10", "mrr", "ndcg@10")
    }
    for name, r in results.items():
        cells = []
        for key in ("recall@5", "recall@10", "mrr", "ndcg@10"):
            value = f"{r[key]:.2f}"
            cells.append(f"**{value}**" if abs(r[key] - best[key]) < 1e-9 else value)
        label = PROVIDER_LABELS.get(name, name)
        if all(abs(r[k] - best[k]) < 1e-9 for k in best):
            label = f"**{label}**"
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return lines


def replace_block(text: str, name: str, lines: list[str], path: Path) -> str:
    begin, end = f"<!-- BEGIN gen:{name} -->", f"<!-- END gen:{name} -->"
    if begin not in text or end not in text:
        raise SystemExit(f"marker {begin!r} / {end!r} missing in {path}")
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    return head + begin + "\n" + "\n".join(lines) + "\n" + end + tail


def main() -> int:
    ablation = json.loads(ABLATION.read_text(encoding="utf-8"))
    bakeoff = json.loads(BAKEOFF.read_text(encoding="utf-8"))
    text = README.read_text(encoding="utf-8")
    text = replace_block(text, "day4-ablation", render_ablation(ablation), README)
    text = replace_block(text, "day4-bakeoff", render_bakeoff(bakeoff), README)
    README.write_text(text, encoding="utf-8")
    print(f"rewrote gen:day4-ablation and gen:day4-bakeoff blocks in {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
