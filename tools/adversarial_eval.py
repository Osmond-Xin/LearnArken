"""Day 8 adversarial eval — live runner, repeated-behavior harness, and Kappa.

Three modes (SPEC day8 §Interfaces 2/5, decision D):

  # live: attack the RAG, judge groundedness (Codex + agy), freeze artifacts
  uv run python tools/adversarial_eval.py --seed 42

  # repeated behavior measurement — MiniMax is non-deterministic at temp 0, so the
  # README before/after numbers are an N-run MEAN, frozen here (INV-5: methodology
  # reproducible + artifact frozen; exact values drift run-to-run, no live judges)
  uv run python tools/adversarial_eval.py --repeat 3 --label after

  # offline & deterministic: re-run "frozen judge labels x human labels -> kappa"
  uv run python tools/adversarial_eval.py --kappa-only

The live run is equivalent to `learnarken eval adversarial`. The kappa step reads
the frozen per-judge artifacts + the human-owned label file (INV-6) and reports
Cohen's Kappa per judge; below the 0.60 soft gate nothing is discarded (decision
A). Until `eval/golden/day8-human-labels.json` exists the kappa step is a no-op
that says so.
"""

from __future__ import annotations

import argparse
import collections
import json
from datetime import UTC, datetime
from pathlib import Path

from learnarken.adversarial import score
from learnarken.adversarial.run import JUDGE_ARTIFACT, REPORT

HUMAN_LABELS = Path("eval/golden/day8-human-labels.json")  # {case_id: grounded_bool}, human-owned
KAPPA_OUT = Path("eval/results/day8-kappa.json")
BEHAVIOR_OUT = "eval/results/day8-behavior-{label}.json"


def repeat_behavior(n: int, label: str) -> dict:
    """Run behavior-only eval n times (no judges) and freeze the mean + per-case
    failure frequency — the reproducible methodology behind the README N-run numbers
    (red-team day8 #4). Non-determinism is inherent, so this reports a distribution,
    not a single point."""
    from learnarken.adversarial import evaluate, load_cases

    cases = load_cases()
    pass_rates: list[float] = []
    fail_counts: collections.Counter[str] = collections.Counter()
    for _ in range(n):
        rows = evaluate(cases, judges=[])
        pass_rates.append(round(sum(r.behavior_pass for r in rows) / len(rows), 4))
        fail_counts.update(r.case_id for r in rows if not r.behavior_pass)
    result = {
        "label": label,
        "generated_at": datetime.now(UTC).isoformat(),
        "n_runs": n,
        "n_cases": len(cases),
        "pass_rate_per_run": pass_rates,
        "mean_pass_rate": round(sum(pass_rates) / n, 4),
        "fail_frequency": dict(fail_counts.most_common()),
        "note": "MiniMax is non-deterministic at temp 0; values drift run-to-run",
    }
    Path(BEHAVIOR_OUT.format(label=label)).write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return result


def calibrate_kappa(judge_names: list[str]) -> dict:
    """Deterministic: frozen judge verdicts x human labels -> Cohen's Kappa."""
    if not HUMAN_LABELS.is_file():
        return {
            "status": "pending",
            "note": (
                f"no human labels at {HUMAN_LABELS} — Yi Xin labels the anchor "
                "(Day 5 answered rows + Day 8 adversarial) before kappa is meaningful "
                "(SPEC decision B; INV-6)."
            ),
        }
    human_raw = json.loads(HUMAN_LABELS.read_text(encoding="utf-8"))
    # Strict: human labels must be JSON booleans (red-team day8 #5 — the string
    # "false" is truthy under bool() and would silently corrupt kappa).
    bad = {k: v for k, v in human_raw.items() if not isinstance(v, bool)}
    if bad:
        raise ValueError(f"human labels must be JSON booleans; non-bool entries: {sorted(bad)}")
    human = dict(human_raw)
    out: dict = {"human_label_n": len(human), "judges": {}}
    for name in judge_names:
        path = Path(JUDGE_ARTIFACT.format(name=name))
        if not path.is_file():
            out["judges"][name] = {"status": "no frozen artifact", "path": str(path)}
            continue
        verdicts = json.loads(path.read_text(encoding="utf-8")).get("verdicts", {})
        judge_labels = {
            cid: v["verdict"] == "grounded"
            for cid, v in verdicts.items()
            if v.get("verdict") in {"grounded", "hallucinated"}
        }
        out["judges"][name] = score.cohen_kappa(human, judge_labels)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--judge", action="append", default=None)
    ap.add_argument(
        "--kappa-only", action="store_true", help="deterministic kappa repro; no live calls"
    )
    ap.add_argument("--repeat", type=int, default=0, help="repeated behavior-only runs (no judges)")
    ap.add_argument("--label", default="run", help="label for the frozen --repeat artifact")
    args = ap.parse_args()
    judge_names = args.judge or ["codex", "agy"]

    if args.repeat:
        result = repeat_behavior(args.repeat, args.label)
        path = BEHAVIOR_OUT.format(label=args.label)
        print(f"wrote {path}: {json.dumps(result, ensure_ascii=False)}")
        return 0

    if not args.kappa_only:
        from learnarken.adversarial import build_report, evaluate, load_cases, write_artifacts
        from learnarken.adversarial.judge import make_judges

        judges = make_judges(judge_names)
        rows = evaluate(load_cases(), judges)
        report = build_report(rows, judges, args.seed)
        write_artifacts(report, judges, REPORT)
        print(
            f"wrote {REPORT} · behavior_pass={report.behavior_pass_rate} · "
            f"intersection_groundedness={report.intersection_groundedness}"
        )

    kappa = calibrate_kappa(judge_names)
    KAPPA_OUT.parent.mkdir(parents=True, exist_ok=True)
    KAPPA_OUT.write_text(json.dumps(kappa, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {KAPPA_OUT}: {json.dumps(kappa, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
