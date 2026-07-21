"""Adversarial-eval orchestration (SPEC day8 §Interfaces 2).

Per case: run the Day 5 answer engine, score behavior deterministically, and —
for answered rows — have each heterogeneous judge score groundedness against the
cited evidence. Judge raw stdout is frozen into per-judge artifacts (decision D /
INV-5). Live LLM/judge calls happen here; tests drive it with ScriptedJudge.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from learnarken.adversarial import score
from learnarken.adversarial.judge import Judge
from learnarken.adversarial.models import AdversarialCase, AdversarialReport, RowResult

GOLDEN = "eval/golden/day8-adversarial.jsonl"
REPORT = Path("eval/results/day8-adversarial-report.json")
JUDGE_ARTIFACT = "eval/results/day8-judge-{name}.json"


def load_cases(path: str = GOLDEN) -> list[AdversarialCase]:
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [AdversarialCase(**r) for r in rows]


def _evidence_map(packages: list[str]) -> dict[str, str]:
    """chunk_id -> full chunk text, over the corpus the engine answers from.

    Uses `corpus_chunks` (text + Day 12 figures) so a figure-cited answer's
    evidence is present for the judge, not skipped (red-team R2 P2)."""
    from learnarken.retrieval import _dedupe_chunks, corpus_chunks

    raw = []
    for pkg in packages:
        raw.extend(corpus_chunks(pkg, strategy="structure"))
    return {c.chunk_id: c.text for c in _dedupe_chunks(raw)}


def _cli_version(name: str) -> str | None:
    try:
        out = subprocess.run(  # noqa: S603 - trusted local CLI
            [name, "--version"], capture_output=True, text=True, timeout=20
        )
        return (
            (out.stdout or out.stderr).strip().splitlines()[0]
            if (out.stdout or out.stderr)
            else None
        )
    except (subprocess.SubprocessError, OSError):
        return None


def evaluate(
    cases: list[AdversarialCase],
    judges: list[Judge],
    *,
    packages: list[str] | None = None,
    answer_fn: Callable | None = None,
) -> list[RowResult]:
    from learnarken.answer.engine import DEFAULT_PACKAGES, answer_question

    pkgs = packages or list(DEFAULT_PACKAGES)
    answer = answer_fn or answer_question
    id_to_text = _evidence_map(pkgs)

    rows: list[RowResult] = []
    for case in cases:
        result = answer(case.question, package_dirs=pkgs)
        cited = [c.chunk_id for c in result.citations]
        evidence = [id_to_text[cid] for cid in cited if cid in id_to_text]

        passed, note = score.behavior_pass(case, result.refused, result.answer_text)
        verdicts = {}
        if not result.refused and evidence:
            for j in judges:
                verdicts[j.name] = j.score(case.question, result.answer_text, evidence)

        rows.append(
            RowResult(
                case_id=case.id,
                category=case.category,
                expected_behavior=case.expected_behavior,
                refused=result.refused,
                refusal_gate=result.refusal_gate,
                answer_text=result.answer_text,
                citations=cited,
                behavior_pass=passed,
                behavior_note=note,
                slipped_gate=score.slipped_gate(case, result.refused, result.refusal_gate),
                judge_verdicts=verdicts,
                grounded_intersection=score.grounded_intersection(verdicts),
                trace_id=result.trace_id,
            )
        )
    return rows


def build_report(rows: list[RowResult], judges: list[Judge], seed: int) -> AdversarialReport:
    return score.aggregate(
        rows,
        seed=seed,
        generated_at=datetime.now(UTC).isoformat(),
        generator_model=_generator_model(),
        judges=[j.name for j in judges],
    )


def _generator_model() -> str | None:
    """The MiniMax model the answers were generated with (honesty: it is the
    thing being judged, and it must never also be the judge)."""
    try:
        from learnarken.llm.minimax import load_minimax_config

        return load_minimax_config().get("MINIMAX_MODEL_NAME")
    except Exception:
        return None


def write_artifacts(
    report: AdversarialReport, judges: list[Judge], report_path: Path = REPORT
) -> None:
    """Freeze the report + one per-judge artifact (model+version+date, decision 3)."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=1), encoding="utf-8")

    for j in judges:
        version = _cli_version(j.name)
        verdicts = {
            r.case_id: r.judge_verdicts[j.name].model_dump()
            for r in report.rows
            if j.name in r.judge_verdicts
        }
        artifact = {
            "judge": j.name,
            "model": getattr(j, "model", None) or "cli-default",  # never null (day8 #13)
            "cli_version": version,
            "generated_at": report.generated_at,
            "errors": report.judge_errors.get(j.name, 0),
            "verdicts": verdicts,
        }
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", j.name)  # path-safe judge id (day8 #10)
        Path(JUDGE_ARTIFACT.format(name=safe)).write_text(
            json.dumps(artifact, indent=1, ensure_ascii=False), encoding="utf-8"
        )
