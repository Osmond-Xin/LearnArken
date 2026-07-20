"""Generate the README benchmark tables from eval artifacts — never hand-edit.

Born from red-team day4 #1: a hand-edited README row was arithmetically
impossible (R@5 > R@10). Extended for #16: the tables are rewritten *in place*
between `<!-- BEGIN gen:... -->` markers, so drift between artifacts and
published tables is structurally impossible. The script refuses to emit any
row that violates Recall monotonicity.

    uv run learnarken eval ablation --json > eval/results/day4-ablation.json
    uv run python tools/dense_bakeoff.py           # also writes day4-bakeoff.json
    uv run python tools/gen_benchmark_tables.py    # rewrites README blocks
    uv run python tools/gen_benchmark_tables.py --check  # verify, no write (CI/test)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ABLATION = Path("eval/results/day4-ablation.json")
DAY11 = Path("eval/results/day11-ablation.json")
DAY11_REFUSAL = Path("eval/results/day11-refusal-gate.json")
BAKEOFF = Path("eval/results/day4-bakeoff.json")
# Rows that can no longer be regenerated (provider removed from the
# architecture) live in their own artifact with provenance — the generator
# owns no numbers of its own (red-team day4 C4).
BAKEOFF_HISTORICAL = Path("eval/results/day4-bakeoff-historical.json")
README = Path("README.md")

MODE_LABELS = {
    "bm25": "bm25 (in-process)",
    "dense": "dense (Vespa + Qwen3-8B)",
    "hybrid": "hybrid (RRF)",
    "hybrid-rerank": "hybrid + rerank",
    "hybrid-graph": "hybrid + graph (3-way RRF)",
    "hybrid-graph-rerank": "hybrid + graph + rerank",
}

PROVIDER_LABELS = {
    "bge-m3": "BGE-M3 (local)",
    "qwen3-8b": "Qwen3-Embedding-8B (local)",
}

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
    n_eval = {r["n_evaluated"] for r in results.values()}
    n_na = {r["n_no_answer"] for r in results.values()}
    if len(n_eval) != 1 or len(n_na) != 1:  # not `assert` — must survive python -O (C11)
        raise SystemExit("REFUSING to emit table: modes evaluated different query sets")

    lines = [
        f"Ranking metrics over **answerable n={n_eval.pop()}**; zero-hit rate over "
        f"the **{n_na.pop()} no-answer traps** (red-team day4 #2 labeling).",
        "",
        *_mode_table(report, ABLATION),
    ]

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


def _mode_table(report: dict, source: Path) -> list[str]:
    """The mode-metrics table body shared by the day4 and day11 blocks."""
    results = report["results"]
    _check_monotonic(results, source)
    lines = [
        "| Mode | Recall@5 | Recall@10 | MRR | nDCG@10 | Zero-hit rate | p50 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    best = {
        k: max(r[k] for r in results.values()) for k in ("recall@5", "recall@10", "mrr", "ndcg@10")
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
    return lines


def render_day11(artifact: dict, refusal: dict) -> list[str]:
    lines: list[str] = []
    for title, key in (
        ("Old golden set (day4, regression guard — dense R@10 was already 1.00)", "old_set"),
        ("New multi-hop set (day11, human-authored, answers span 2-3 DMs)", "multihop_set"),
    ):
        report = artifact[key]
        n_eval = {r["n_evaluated"] for r in report["results"].values()}
        n_na = {r["n_no_answer"] for r in report["results"].values()}
        if len(n_eval) != 1 or len(n_na) != 1:
            raise SystemExit("REFUSING to emit table: modes evaluated different query sets")
        lines += [
            f"**{title}** — answerable n={n_eval.pop()}, no-answer traps n={n_na.pop()}:",
            "",
            *_mode_table(report, DAY11),
            "",
        ]
    gate = refusal["modes"]
    lines += [
        f"T3 refusal-regression gate (deterministic threshold gate over "
        f"{refusal['n_traps']} no-answer traps): hybrid "
        f"{gate['hybrid']['refusal_rate']:.2f} vs hybrid+graph "
        f"{gate['hybrid-graph']['refusal_rate']:.2f} — "
        + ("**pass** (not lower)." if refusal["pass"] else "**FAIL**."),
    ]
    revisions = artifact["multihop_set"].get("model_revisions")
    if revisions:
        lines += ["", f"Model snapshots pinned (INV-5): {_short_revisions(revisions)}."]
    return lines


def render_bakeoff(report: dict, historical: dict) -> list[str]:
    results = {name: r["overall"] for name, r in report["results"].items()}
    _check_monotonic(results, BAKEOFF)
    _check_monotonic({historical["provider_label"]: historical["metrics"]}, BAKEOFF_HISTORICAL)
    h = historical["metrics"]
    lines = [
        "| Provider | Recall@5 | Recall@10 | MRR | nDCG@10 |",
        "| --- | --- | --- | --- | --- |",
        f"| {historical['provider_label']} | {h['recall@5']:.2f} | {h['recall@10']:.2f} "
        f"| {h['mrr']:.2f} | {h['ndcg@10']:.2f} |",
    ]
    best = {
        k: max(r[k] for r in results.values()) for k in ("recall@5", "recall@10", "mrr", "ndcg@10")
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


def main(argv: list[str] | None = None) -> int:
    check_only = "--check" in (argv if argv is not None else sys.argv[1:])
    ablation = json.loads(ABLATION.read_text(encoding="utf-8"))
    day11 = json.loads(DAY11.read_text(encoding="utf-8"))
    day11_refusal = json.loads(DAY11_REFUSAL.read_text(encoding="utf-8"))
    bakeoff = json.loads(BAKEOFF.read_text(encoding="utf-8"))
    historical = json.loads(BAKEOFF_HISTORICAL.read_text(encoding="utf-8"))
    current = README.read_text(encoding="utf-8")
    text = replace_block(current, "day4-ablation", render_ablation(ablation), README)
    text = replace_block(text, "day11-ablation", render_day11(day11, day11_refusal), README)
    text = replace_block(text, "day4-bakeoff", render_bakeoff(bakeoff, historical), README)
    if check_only:
        if text != current:
            print(
                f"MISMATCH: {README} tables differ from the eval artifacts — "
                "re-run tools/gen_benchmark_tables.py (red-team day4 C4)"
            )
            return 1
        print(f"{README} tables match the eval artifacts")
        return 0
    README.write_text(text, encoding="utf-8")
    print(f"rewrote gen:day4-ablation, gen:day11-ablation and gen:day4-bakeoff blocks in {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
