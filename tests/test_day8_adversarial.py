"""Day 8 adversarial-eval tests (docs/specs/day8.md).

All hermetic: no live LLM or judge CLIs. The orchestration is exercised with a
stub generator + ScriptedJudge; a skip-marked live suite drives the real CLIs.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from learnarken.adversarial import score
from learnarken.adversarial.judge import (
    FORBIDDEN_JUDGES,
    CLIJudge,
    ScriptedJudge,
    build_judge_prompt,
    parse_judge_output,
)
from learnarken.adversarial.models import AdversarialCase, JudgeVerdict
from learnarken.adversarial.run import evaluate, load_cases

GOLDEN = "eval/golden/day8-adversarial.jsonl"


# --- golden set integrity (INV-3: enumerated, four classes) -----------------


def test_golden_has_at_least_30_across_four_categories():
    cases = load_cases(GOLDEN)
    assert len(cases) >= 30
    cats = {c.category for c in cases}
    assert cats == {"rewrite-invariance", "perturbation", "no-answer", "cross-doc"}
    assert len({c.id for c in cases}) == len(cases)  # unique ids
    for c in cases:
        assert c.expected_behavior in {"answer", "refuse", "clarify"}
        assert c.attack_note  # every row documents its attack (INV-3)


# --- behavior scoring (deterministic, no LLM) -------------------------------


def _case(behavior, anchor):
    return AdversarialCase(
        id="t",
        category="perturbation",
        question="q",
        expected_behavior=behavior,
        attack_note="n",
        anchor=anchor,
    )


@pytest.mark.parametrize(
    "behavior,anchor,refused,answer,expected",
    [
        # answer: must answer + state required fact + avoid forbidden
        ("answer", {"must_state": ["25 Nm"]}, False, "torque is 25 Nm", True),
        ("answer", {"must_state": ["25 Nm"]}, False, "torque is high", False),
        ("answer", {"must_state": ["25 Nm"]}, True, "", False),  # false refusal
        # refuse: must refuse
        ("refuse", {"must_not_state": ["25 Nm"]}, True, "idk", True),
        ("refuse", {"must_not_state": ["25 Nm"]}, False, "it is 25 Nm", False),  # DEFECT
        # clarify: refuse OR answer-without-affirming-false
        ("clarify", {"must_not_state": ["30 Nm"]}, True, "idk", True),
        ("clarify", {"must_not_state": ["30 Nm"]}, False, "actually it is 25 Nm", True),
        ("clarify", {"must_not_state": ["30 Nm"]}, False, "yes, 30 Nm", False),  # DEFECT
        # negation-aware: mentioning the wrong value to REJECT it is a correction,
        # not an affirmation (the scorer bug caught while measuring the Day 8 fix)
        (
            "clarify",
            {"must_not_state": ["30 Nm"], "must_state": ["25 Nm"]},
            False,
            "It is 25 Nm, not 30 Nm as stated.",
            True,
        ),
        (
            "clarify",
            {"must_not_state": ["30 Nm"], "must_state": ["25 Nm"]},
            False,
            "Yes, 30 Nm is correct.",
            False,
        ),  # bare affirmation, no correction
        # answer case: forbidden value rejected via negation is not a failure
        (
            "answer",
            {"must_state": ["25 Nm"], "must_not_state": ["30 Nm"]},
            False,
            "The torque is 25 Nm, not 30 Nm.",
            True,
        ),
    ],
)
def test_behavior_pass(behavior, anchor, refused, answer, expected):
    passed, _ = score.behavior_pass(_case(behavior, anchor), refused, answer)
    assert passed is expected


def test_slipped_gate_flags_a_trap_answered_through_all_gates():
    c = _case("refuse", {"must_not_state": ["25 Nm"]})
    assert score.slipped_gate(c, refused=False, refusal_gate=None) is not None
    assert score.slipped_gate(c, refused=True, refusal_gate="threshold") is None


# --- judge intersection + disagreement (SPEC decision C) --------------------


def _verdict(name, verdict):
    return JudgeVerdict(judge=name, verdict=verdict)


def test_grounded_intersection_requires_all_judges():
    both = {"codex": _verdict("codex", "grounded"), "gemini": _verdict("gemini", "grounded")}
    one_bad = {"codex": _verdict("codex", "grounded"), "gemini": _verdict("gemini", "hallucinated")}
    assert score.grounded_intersection(both) is True
    assert score.grounded_intersection(one_bad) is False
    assert score.grounded_intersection({}) is None  # nothing to judge (refusal)
    assert score.judges_disagree(one_bad) is True
    assert score.judges_disagree(both) is False


# --- judge prompt / parsing -------------------------------------------------


def test_judge_prompt_spotlights_untrusted_inputs():
    p = build_judge_prompt("q?", "the answer", ["ev one", "ev two"], nonce="abc123")
    # untrusted inputs are inside a passive-DATA delimiter (red-team day8 #3)
    assert "passive DATA" in p
    assert "the answer" in p and "ev one" in p
    assert "abc123" in p  # nonce embedded (red-team day8 #2)
    assert "world knowledge" in p


def test_parse_judge_output_strict_verdict_and_nonce():
    raw = (
        "reasoning...\n"
        '{"nonce":"N1","claims":[{"claim":"x","supported":true}],'
        '"verdict":"grounded","groundedness":1.0}\n'
        "bye"
    )
    assert parse_judge_output(raw, "N1")["verdict"] == "grounded"
    with pytest.raises(ValueError):
        parse_judge_output("no json here")
    # a prompt-echo of the instruction's example (verdict "grounded|hallucinated")
    # must NOT be accepted as a verdict (red-team day8 #2)
    echo = '{"claims":[{"supported":true}],"verdict":"grounded|hallucinated","reasoning":""}'
    with pytest.raises(ValueError):
        parse_judge_output(echo)
    # wrong nonce is rejected even with a valid verdict
    with pytest.raises(ValueError):
        parse_judge_output('{"nonce":"WRONG","verdict":"grounded"}', "N1")


# --- heterogeneity: MiniMax (the generator) is a forbidden judge ------------


def test_minimax_family_is_never_a_judge():
    assert "minimax" in FORBIDDEN_JUDGES
    for name in ("minimax", "MiniMax", "minimax-m3", "MiniMax-Text-01"):
        with pytest.raises(ValueError):
            CLIJudge(name)  # substring family check (red-team day8 #7)
    with pytest.raises(ValueError):
        CLIJudge("nope-unknown")  # unknown judge → clear error, not KeyError


def test_judge_error_fails_closed_in_intersection():
    # red-team day8 #1: an errored judge must not be dropped — the row is NOT grounded
    verdicts = {
        "codex": JudgeVerdict(judge="codex", verdict="grounded"),
        "agy": JudgeVerdict(judge="agy", verdict="error"),
    }
    assert score.grounded_intersection(verdicts) is False


# --- Cohen's Kappa (SPEC decisions A/B/T3) ----------------------------------


def test_cohen_kappa_normal_and_skew_trap():
    normal = score.cohen_kappa(
        {"1": True, "2": False, "3": True, "4": False},
        {"1": True, "2": False, "3": False, "4": False},
    )
    assert normal["kappa"] is not None and normal["n"] == 4
    # single-class (all grounded) -> kappa undefined, not a fake high agreement
    skew = score.cohen_kappa({"1": True, "2": True, "3": True}, {"1": True, "2": True, "3": True})
    assert skew["kappa"] is None and skew["agreement"] == 1.0 and "skew trap" in skew["note"]


# --- anti-leak (SPEC decision 9 / DR §7 坑1) --------------------------------


def test_adversarial_set_does_not_leak_into_the_answer_prompt():
    # static prompt carries no few-shot examples...
    from learnarken.answer.prompt import build_system, make_delimiter

    system = build_system(make_delimiter())
    for case in load_cases(GOLDEN):
        assert case.question not in system, f"{case.id} leaked into the generation prompt"


def test_generator_only_ever_sees_the_question_not_the_anchors(monkeypatch):
    # ...and the harness passes ONLY case.question to the generator — never the
    # expected_behavior / attack_note / must_state anchors (red-team day8 #9).
    monkeypatch.setattr("learnarken.adversarial.run._evidence_map", lambda pkgs: {"c1": "text"})
    seen: list[str] = []

    def spy_answer(question, package_dirs=None):
        seen.append(question)
        return SimpleNamespace(
            refused=True,
            refusal_gate="llm",
            answer_text="I don't know.",
            citations=[],
            trace_id="t",
        )

    cases = load_cases(GOLDEN)[:5]
    evaluate(cases, judges=[], answer_fn=spy_answer)
    # The generator sees EXACTLY the questions — nothing else. (must_state /
    # must_not_state can legitimately appear in a perturbation question, so the
    # meaningful leak check is on the pure-metadata fields.)
    assert seen == [c.question for c in cases]
    blob = "\n".join(seen)
    for c in cases:
        assert c.attack_note not in blob
        assert c.id not in blob


# --- hermetic orchestration (stub generator + scripted judges) --------------


def test_evaluate_end_to_end_hermetic(monkeypatch):
    # Control the evidence map so scripted judges see known chunk text.
    monkeypatch.setattr(
        "learnarken.adversarial.run._evidence_map",
        lambda pkgs: {"c1": "The mounting bolts are torqued to 25 Nm."},
    )

    def fake_answer(question, package_dirs=None):
        if "LA-29-4711-2" in question:  # a perturbation trap the system wrongly answers
            return SimpleNamespace(
                refused=False,
                refusal_gate=None,
                answer_text="It is 25 Nm.",
                citations=[SimpleNamespace(chunk_id="c1")],
                trace_id="tr1",
            )
        if "cabin pressurization" in question:  # a no-answer trap correctly refused
            return SimpleNamespace(
                refused=True,
                refusal_gate="llm",
                answer_text="I don't know.",
                citations=[],
                trace_id="tr2",
            )
        return SimpleNamespace(
            refused=False,
            refusal_gate=None,
            answer_text="Torqued to 25 Nm.",
            citations=[SimpleNamespace(chunk_id="c1")],
            trace_id="tr3",
        )

    cases = [
        AdversarialCase(
            id="A",
            category="rewrite-invariance",
            question="bolt torque?",
            expected_behavior="answer",
            attack_note="n",
            anchor={"must_state": ["25 Nm"]},
        ),
        AdversarialCase(
            id="B",
            category="perturbation",
            question="torque LA-29-4711-2?",
            expected_behavior="refuse",
            attack_note="n",
            anchor={"must_not_state": ["25 Nm"]},
        ),
        AdversarialCase(
            id="C",
            category="no-answer",
            question="cabin pressurization schedule",
            expected_behavior="refuse",
            attack_note="n",
            anchor={},
        ),
    ]
    judges = [
        ScriptedJudge("codex", {"*": {"verdict": "grounded"}}),
        ScriptedJudge(
            "gemini", {"It is 25 Nm.": {"verdict": "hallucinated"}, "*": {"verdict": "grounded"}}
        ),
    ]
    rows = evaluate(cases, judges, answer_fn=fake_answer)

    by_id = {r.case_id: r for r in rows}
    assert by_id["A"].behavior_pass is True  # answered with required fact
    assert by_id["B"].behavior_pass is False  # trap answered -> defect
    assert by_id["B"].slipped_gate is not None
    assert by_id["C"].behavior_pass is True  # trap refused
    assert by_id["C"].grounded_intersection is None  # nothing to judge
    # Judges disagree on B's answer -> intersection is False (strict headline).
    assert by_id["B"].grounded_intersection is False

    report = score.aggregate(
        rows, seed=1, generated_at="t", generator_model="minimax-m3", judges=["codex", "gemini"]
    )
    assert report.n == 3
    assert "B" in report.inter_judge_disagreements
    assert report.generator_model == "minimax-m3"  # honesty: the judged model is recorded


# --- skip-marked live suite (real CLIs) -------------------------------------

LIVE = os.environ.get("LEARNARKEN_LIVE_JUDGES") == "1"


@pytest.mark.skipif(not LIVE, reason="needs LEARNARKEN_LIVE_JUDGES=1 and codex/gemini CLIs")
def test_live_judge_returns_a_verdict():
    j = CLIJudge("codex")
    v = j.score(
        "What torque?", "The bolts are torqued to 25 Nm.", ["The bolts are torqued to 25 Nm."]
    )
    assert v.verdict in {"grounded", "hallucinated", "error"}
    assert v.raw or v.verdict == "error"
