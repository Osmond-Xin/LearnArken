"""INV-6 probe: how often does the contract re-ask actually recover?

The re-ask was ruled on 2026-07-28 and shipped in three steps (F-33 / F-40 /
F-44). Its *overall* effectiveness is recorded in the review as **not
sufficiently measured** — one observed success. This probe is the instrument
for raising that number; it is meant to be run by the human, not the
implementer, because the number is an INV-6 number.

**Read this before spending on it.** The denominator is not the number of runs.
A run only says something about the re-ask if attempt 1 *fails the contract*,
and that was measured at roughly 1 query in 12. So ~12 generations buy ~1
observation. Runs where attempt 1 succeeds cost a full generation and
contribute nothing but a tighter estimate of the base rate. Budget accordingly,
and read the tally as the raw counts it prints — not as a rate.

It is not even the number of *generations* unless every run reached the model.
A question the retrieval threshold refuses never calls it, so it cannot fail the
contract however the model behaves; those land in `no_generation`, and the
tally reports ``runs=``, ``reached the model=`` and ``refused before it=``
separately (plus ``unknown=`` when a run's outcome could not be determined).
A third of Yi Xin's 2026-07-28 run was such runs, all from one query, all
silently counted as clean — an inflated denominator produced by the very tool
built to prevent one.

What is observed, per run, from two genuinely independent readings:

- **the stream** — a ``restart`` event with reason ``llm-contract`` means
  attempt 1 broke the contract, the retry was funded, and attempt 2 is running.
- **the trace** — ``llm.recovered_after_contract_failure`` on a run that
  finished, or ``llm.contract_error`` on one that refused. (Top level: spans
  are splatted into the trace root by `write_trace`, not nested under `spans` —
  reading the wrong path silently turns the cross-check into no check at all,
  which is exactly what the first version of this file did.)

They are cross-checked rather than merged, over the full matrix of outcomes. A
disagreement, a missing trace, a run whose outcome could not be determined, a
paid run with no logged outcome, or a sample in which the re-ask never fired at
all makes the whole thing **UNQUOTABLE** and exits non-zero: under INV-4 a
number with a hole in its evidence is not a smaller number, it is not a number.
That last case matters most — "24 runs, nothing went wrong" is a reading of the
base rate and no reading whatsoever of recovery.

Prerequisites: the live stack and a working ``.env`` — run
``uv run python tools/demo_preflight.py`` first; it prints the fix for whatever
is missing. This calls the paid endpoint on every run.

Usage::

    uv run python tools/probe_retry_effectiveness.py --runs 24 \\
        --out eval/results/probe-retry-2026-07-28.jsonl

``--runs`` is what this session spends, not a target total; the banner printed
before the first call states the session/total accounting and the worst-case
paid-generation count, so a resume cannot quietly buy more than intended.

Each run is logged twice — ``start`` before the call, ``run`` after it — and
flushed, so a probe stopped with ^C keeps every observation it paid for *and*
records the one it paid for but never saw the end of. Re-run the same command
with ``--resume`` to continue; the tally counts both sessions and refuses to
quote if any paid run is left unaccounted. Run numbers are allocated above
every id ever seen, so a resumed session can never reuse — and thereby erase —
the number of a run that was paid for and never finished.

The log carries a ``LOG_VERSION`` and is only resumable by the build that wrote
it: rows carry the verdicts of the logic that produced them, and this file has
already shipped one version whose cross-check read the wrong trace key and so
agreed with everything. Derived fields are recomputed on load for the same
reason. The session holds an exclusive lock on the log, and a new log is
created exclusively, so two probes cannot interleave into one artifact. An
existing file is never overwritten (ADR-0004: a measurement is never silently
replaced).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from learnarken.answer.trace import TRACE_DIR, read_trace  # noqa: E402
from learnarken.api.app import app  # noqa: E402

# Cycled, so the sample is not one prompt repeated: a contract failure is a
# generation glitch, but its rate may well depend on how much evidence the
# prompt carries, and one query could not show that.
#
# The demo's third query — "How do I replace the coffee maker in the galley?" —
# was in this list and has been removed. Yi Xin's 2026-07-28 run showed it is
# refused by the retrieval threshold gate on all 8 of its 8 runs, so it never
# reaches the model and *cannot* produce a contract failure. It was inflating
# the sample by a third while buying nothing. `no_generation` below catches the
# same condition for any query, because which prompts clear the threshold is a
# property of the corpus and will change without this list changing.
QUERIES = [
    ("answer", "What safety precautions apply before removing the hydraulic pump?"),
    ("retraction", "APU automatic start sequence"),
]

#: Outcomes that mean the run did not yield a reading. They are not zeroes; a
#: sample containing one cannot be quoted until it is explained.
INDETERMINATE = (
    "retried_indeterminate",
    "transport_error",
    "non_observation",
    "incoherent_result",
)

#: Bumped whenever the classification, cross-check, or row schema changes. A
#: log is only resumable by the build that wrote it — see `load_prior`.
LOG_VERSION = "probe-retry/9"

#: `new_trace_id()` is a timestamp plus eight hex characters. Anything else is
#: not an id this run produced, and must never become a path (2026-07-28 P2).
TRACE_ID_RE = re.compile(r"^[0-9A-Za-z]+-[0-9a-f]{8}$")

#: The nested keys `read_back_trace` always writes when it read a trace. A
#: `trace_llm` missing any of them is a partial reading, not a silent one.
TRACE_FIELDS = ("recovered_after_contract_failure", "contract_error", "first_attempt_error")


def parse_sse(body: str) -> list[tuple[str, str]]:
    """Split an SSE body into ``(event, data)`` frames.

    Framed rather than line-by-line: the previous version attributed every
    ``data:`` line to the last ``event:`` line it had seen anywhere in the body,
    which happens to work only because this producer emits exactly one of each
    per frame. Multi-line data, a frame with no data, or a comment line would
    have silently mis-attributed a payload — and a mis-read `restart` is a wrong
    recovery count, not a crash.
    """
    frames = []
    # SSE allows CRLF, CR or LF line endings. This producer emits LF, but a
    # proxy that rewrites them would otherwise merge every frame into one block
    # and hide the `restart` inside it.
    for block in body.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
        event, data = None, []
        for line in block.splitlines():
            if line.startswith(":") or not line.strip():
                continue  # comment / keep-alive
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                event = value
            elif field == "data":
                data.append(value)
        if event is not None:
            frames.append((event, "\n".join(data)))
    return frames


def _unreadable(note: str, status: int | None, restarts: int = 0, tokens: int = 0) -> dict:
    """A row that records a paid call which produced no reading of the model."""
    return {
        "trace_id": None,
        "http_status": status,
        "transport_note": note,
        "refused": None,
        "refusal_gate": None,
        "stream_error": None,
        "stream_restarts": restarts,
        "token_events": tokens,
        "saw_result": False,
        "trace_llm": None,
        "trace_outcome": None,
        "trace_spans": None,
        "trace_note": "no readable result to trace",
    }


def run_once(client: TestClient, question: str) -> dict:
    """One real query. Returns what the stream said and what the trace said."""
    try:
        response = client.post("/query", json={"question": question})
    except Exception as exc:
        # The call may already have been billed before the app raised. Losing
        # the session to a traceback would throw away every run logged so far.
        return _unreadable(f"request raised: {type(exc).__name__}: {exc}", None)

    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or not content_type.startswith("text/event-stream"):
        # A gate refusal (403 without the demo key), a 500, a proxy error page:
        # no events at all parses as a flawless run, so this must be caught
        # here. Not an observation of the model — an observation of the harness.
        return _unreadable(
            f"not an SSE response (content-type {content_type!r})", response.status_code
        )

    restarts = tokens = 0
    result: dict = {}
    saw_result = False
    error = None
    for event, data in parse_sse(response.text):
        if event == "token":
            tokens += 1
            continue
        try:
            payload = json.loads(data) if data else {}
        except json.JSONDecodeError as exc:
            # A truncated body mid-frame. Crashing here would lose the runs
            # already logged this session; guessing the payload would be worse.
            return _unreadable(
                f"undecodable {event!r} frame: {exc}", response.status_code, restarts, tokens
            )
        if event in ("restart", "result", "error") and not isinstance(payload, dict):
            # `[]` and `"x"` are valid JSON. Calling `.get()` on them raises
            # after the call was already paid for and its `start` line flushed,
            # leaving a run with no outcome row (red-team round 6 P2).
            return _unreadable(
                f"{event!r} frame is not an object: {payload!r}",
                response.status_code,
                restarts,
                tokens,
            )
        if event == "restart" and payload.get("reason") == "llm-contract":
            restarts += 1
        elif event == "result":
            result, saw_result = payload, True
        elif event == "error":
            message = payload.get("message")
            if not isinstance(message, str) or not message.strip():
                # An error frame the probe cannot read is still an error frame.
                # Storing a non-string here produced a row that `run_once` wrote
                # and `validate_run_row` later refused — a log the tool itself
                # could not resume (red-team round 7 P2).
                return _unreadable(
                    f"malformed error frame: message={message!r}",
                    response.status_code,
                    restarts,
                    tokens,
                )
            error = message

    if saw_result and (note := malformed_result(result)):
        # The result object is the authority on what the run decided. Defaulting
        # its fields with `.get()` and classifying the defaults would turn a
        # malformed refusal into a recovery (red-team round 5 P1).
        return _unreadable(
            f"malformed result object: {note}", response.status_code, restarts, tokens
        )

    observed = {
        "trace_id": result.get("trace_id"),
        "http_status": response.status_code,
        "refused": result.get("refused"),
        "refusal_gate": result.get("refusal_gate"),
        "token_events": tokens,
        "stream_restarts": restarts,
        "saw_result": saw_result,
        "stream_error": error,
    }
    observed.update(read_back_trace(result.get("trace_id"), question))
    return observed


def malformed_result(result: dict) -> str | None:
    """Say why a `result` payload cannot be read, or None if it can.

    Deliberately does not police *which* gates exist: a gate name this build has
    not seen is a refusal for a reason other than `llm-contract`, which
    classifies correctly. What must be rejected is a payload whose two
    statements about the decision cannot both be read — an empty-string gate,
    a non-boolean `refused`.
    """
    refused, gate = result.get("refused"), result.get("refusal_gate")
    if not isinstance(refused, bool):
        return f"refused={refused!r} is not a boolean"
    if gate is not None and (not isinstance(gate, str) or not gate.strip()):
        return f"refusal_gate={gate!r} is neither null nor a gate name"
    trace_id = result.get("trace_id")
    if not isinstance(trace_id, str) or not TRACE_ID_RE.match(trace_id):
        # Not merely "a string": this value becomes a filename. A path-like id
        # would let a result point the second reading at an unrelated trace and
        # collect it as corroboration (2026-07-28 P2).
        return f"trace_id={trace_id!r} is not an id this run could have produced"
    return None


def read_back_trace(trace_id: str | None, question: str | None = None) -> dict:
    """The second reading, bound to the run that asked for it.

    Absent or unreadable is reported, never guessed. `question` is checked
    against the trace's own record of what was asked: an id match alone lets a
    *stale* trace for a different question — one that happens to record a
    recovered re-ask — be collected as this run's corroboration (2026-07-28 P1).
    """
    if not trace_id or not TRACE_ID_RE.match(trace_id):
        # This value becomes a filename. A path-like id would let a result point
        # the second reading at an unrelated trace and collect it as
        # corroboration for a run it says nothing about (2026-07-28 P2).
        return {
            "trace_llm": None,
            "trace_outcome": None,
            "trace_spans": None,
            "trace_note": f"no usable trace id in result ({trace_id!r})",
        }
    path = TRACE_DIR / f"{trace_id}.json"
    if not path.exists():
        return {
            "trace_llm": None,
            "trace_outcome": None,
            "trace_spans": None,
            "trace_note": f"trace not written ({path})",
        }
    try:
        # Spans live at the trace root — `write_trace` splats them next to
        # `format` and `trace_id`. There is no `spans` key to read.
        trace = read_trace(path)
    except Exception as exc:  # unreadable is a finding, not a crash
        return {
            "trace_llm": None,
            "trace_outcome": None,
            "trace_spans": None,
            "trace_note": f"unreadable: {exc}",
        }
    if question is not None and trace.get("question") != question:
        return {
            "trace_llm": None,
            "trace_outcome": None,
            "trace_spans": None,
            "trace_note": "trace records a different question than this run asked",
        }
    if trace.get("trace_id") != trace_id:
        # The file's own id must match the one the stream reported, or the
        # second reading is a different run's evidence wearing this run's name.
        return {
            "trace_llm": None,
            "trace_outcome": None,
            "trace_spans": None,
            "trace_note": f"trace names {trace.get('trace_id')!r}, the result named {trace_id!r}",
        }
    if "llm" not in trace:
        # An absent llm span is legitimate only for a gate that refused *before*
        # the model was called; the engine writes the span the moment generation
        # starts. Accepting it for any trace let an answered run with a corrupt
        # trace pass as a real second reading (red-team round 7 P1).
        outcome = trace.get("outcome")
        # Decided by the trace's *structure*, not by a gate's name: the engine
        # writes `llm` the moment generation starts, so neither span means the
        # model was never called — whichever gate refused, and whatever gates
        # exist in a later build. Naming the gate here made the probe depend on
        # one engine revision and fail closed on any other (Yi Xin's ruling 5,
        # 2026-07-28).
        pre_model = (
            isinstance(outcome, dict)
            and outcome.get("refused") is True
            and "generation" not in trace
        )
        if not pre_model:
            return {
                "trace_llm": None,
                "trace_outcome": None,
                "trace_spans": None,
                "trace_note": "trace has no llm span but reached the model",
            }
        return _second_reading(trace, dict.fromkeys(TRACE_FIELDS))
    llm = trace["llm"]
    if not isinstance(llm, dict):
        # A present-but-malformed span is not an absent one, and `or {}`
        # collapsed both into "nothing recorded" (red-team round 6 P1).
        return {
            "trace_llm": None,
            "trace_outcome": None,
            "trace_spans": None,
            "trace_note": f"trace llm span is not an object: {llm!r}",
        }
    second = {field: llm.get(field) for field in TRACE_FIELDS}
    for field, value in second.items():
        # `disagrees` reads presence as affirmative evidence, so a falsy
        # non-string — `false`, `0`, `""` — would be read as "no event
        # recorded" or as an event, depending on nothing (round 5 P1).
        if value is not None and (not isinstance(value, str) or not value.strip()):
            return {
                "trace_llm": None,
                "trace_outcome": None,
                "trace_spans": None,
                "trace_note": f"trace {field}={value!r} is not a reason",
            }
    return _second_reading(trace, second)


def _second_reading(trace: dict, span: dict) -> dict:
    """Pair the llm span with the decision the trace recorded, or refuse both.

    A reading without a readable decision would silently switch the
    final-decision cross-check off while the ratio kept printing — the check
    would be present in the code and absent from the evidence (round 10 P1).
    """
    decision = _trace_outcome(trace)
    if decision is None:
        return {
            "trace_llm": None,
            "trace_outcome": None,
            "trace_spans": None,
            "trace_note": "trace records no readable outcome",
        }
    return {
        "trace_llm": span,
        "trace_outcome": decision,
        # The raw fact, not merely the absence of contract fields: "no model
        # span existed" is what makes a threshold run un-billable, and
        # collapsing it into "no contract event recorded" cannot tell the two
        # apart (red-team 2026-07-28 P1/P2).
        "trace_spans": {"llm": "llm" in trace, "generation": "generation" in trace},
        "trace_note": None,
    }


def _trace_outcome(trace: dict) -> dict | None:
    """The decision the trace recorded, for cross-checking against the stream.

    The llm span alone does not say what the run *decided*. A threshold refusal
    writes a legitimately silent span, so a `clean` stream row paired with a
    refusing trace agreed on the span and disagreed on everything that mattered
    (red-team round 9 P2).
    """
    outcome = trace.get("outcome")
    if not isinstance(outcome, dict) or not isinstance(outcome.get("refused"), bool):
        return None
    gate = outcome.get("gate")
    return {"refused": outcome["refused"], "gate": gate if isinstance(gate, str) else None}


def classify(row: dict) -> str:
    """One of six outcomes, decided by the stream reading.

    Order matters. A run that re-asked and then died in transport has a
    ``restart`` and no ``result``, so a restart-first test scores it as a
    recovery — a confidently wrong reading of the exact number this probe
    exists to produce. Indeterminacy is checked first and kept out of the
    denominator.

    ``retried_recovered`` is deliberately not "not refused": a run can re-ask
    successfully and then still refuse at a *later* gate — citation
    verification, say. That is the re-ask working, and counting it as a failure
    would understate the thing being measured.
    """
    if row.get("transport_note"):
        return "non_observation"
    if row.get("stream_error") or not row.get("saw_result"):
        return "retried_indeterminate" if row.get("stream_restarts") else "transport_error"
    if row.get("stream_restarts", 0) > 1:
        # The engine re-asks exactly once. More restarts than that means the
        # producer is not the one this classification was written against, so
        # the run is not evidence about a single re-ask (red-team round 3 P2).
        return "retried_indeterminate"
    if bool(row.get("refused")) != (row.get("refusal_gate") is not None):
        # `refused` and `refusal_gate` are two statements about one decision.
        # When they disagree, the result object does not describe an outcome
        # this classification knows how to read — and reading `refusal_gate`
        # alone would score a refusal as a recovery (red-team round 4 P1).
        return "incoherent_result"
    spans = row.get("trace_spans")
    if (
        isinstance(spans, dict)
        and not spans["llm"]
        and not spans["generation"]
        and row.get("refused")
        and not row.get("stream_restarts")
        and not row.get("token_events")
    ):
        # A gate refused before generation, so this run could not have produced
        # a contract failure whatever the model does. It is a determinate,
        # legitimate observation — and it is *not* a zero in the denominator.
        # Counting it as `clean` inflated a sample by a third while buying
        # nothing (Yi Xin's 2026-07-28 run).
        #
        # The trace decides this one, because the stream cannot: a model that
        # answers "I cannot answer" also refuses with no text. Which gate did it
        # is not consulted, so a gate this build has never heard of classifies
        # correctly instead of failing closed (ruling 5).
        return "no_generation"
    contract_refusal = row.get("refusal_gate") == "llm-contract"
    if row.get("stream_restarts"):
        return "retried_failed" if contract_refusal else "retried_recovered"
    if contract_refusal:
        # No restart and a contract refusal: attempt 1 failed in a class the
        # engine does not re-ask (truncation), or the retry was not funded.
        return "not_retried"
    return "clean"


def disagrees(row: dict) -> bool:
    """Does the trace contradict the stream, over the whole outcome matrix?

    Two readings are only worth taking if every combination is checked. A
    partial matrix means the states it omits pass as agreement, which is the
    failure mode a second reading is supposed to catch.
    """
    trace = row.get("trace_llm")
    if trace is None:
        return False  # a gap, not a contradiction — `tally` blocks on it separately
    decision = row.get("trace_outcome")
    if decision is not None and row.get("saw_result"):
        # The two readings must agree about what the run *decided*, not only
        # about the llm span. A threshold refusal writes a legitimately silent
        # span, so span-only agreement said nothing (red-team round 9 P2).
        if decision["refused"] != bool(row.get("refused")):
            return True
        if decision["refused"] and decision["gate"] != row.get("refusal_gate"):
            return True
    spans = row.get("trace_spans")
    if not isinstance(spans, dict):
        return True  # a reading without its raw span facts is not a reading
    if row["outcome"] == "no_generation":
        # Not merely "no contract event recorded" — *no model span existed*.
        # Collapsing it into the clean case would let a future engine change
        # that moves `refuse("threshold")` after generation stay quotable as a
        # run that never called the model (red-team 2026-07-28 P2).
        if spans["llm"] or spans["generation"]:
            return True
    elif not spans["llm"]:
        # The mirror of the above, and the hole it left: a stray `token` frame
        # before a threshold refusal made the run `clean`, and a trace showing
        # no model span agreed with it. Every other determinate outcome asserts
        # the model ran, so the trace must show that it did.
        return True
    recovered = trace.get("recovered_after_contract_failure") is not None
    contract_error = trace.get("contract_error") is not None
    first_attempt = trace.get("first_attempt_error") is not None
    expected = {
        # outcome: (recovered, contract_error, first_attempt_error)
        "clean": (False, False, False),
        "no_generation": (False, False, False),  # the model was never called
        "retried_recovered": (True, False, False),
        "retried_failed": (False, True, True),
        "not_retried": (False, True, False),
    }.get(row["outcome"])
    if expected is None:
        return False  # indeterminate rows are excluded, not adjudicated
    return (recovered, contract_error, first_attempt) != expected


def tally(rows: list[dict], unfinished: int = 0) -> tuple[str, bool]:
    """Render the counts, and say whether the sample may be quoted."""

    def complete(row: dict) -> bool:
        """A second reading is all three parts or none of them."""
        return (
            row.get("trace_llm") is not None
            and row.get("trace_outcome") is not None
            and isinstance(row.get("trace_spans"), dict)
        )

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    recovered = counts.get("retried_recovered", 0)
    retried = recovered + counts.get("retried_failed", 0)
    conflicts = [r for r in rows if r.get("disagreement")]
    # `complete` rather than `trace_llm is not None`: a row carrying part of a
    # second reading is not carrying one. Replay rejects those, but `tally` is
    # what decides quotability and must not depend on having been called after
    # a validator (red-team 2026-07-28 P3).
    gaps = [r for r in rows if not complete(r) and r["outcome"] not in INDETERMINATE]
    indeterminate = sum(counts.get(name, 0) for name in INDETERMINATE)

    blockers = []
    if conflicts:
        blockers.append(f"stream and trace disagree on {len(conflicts)} run(s)")
    if gaps:
        blockers.append(f"{len(gaps)} run(s) have no second reading (trace missing/unreadable)")
    if indeterminate:
        blockers.append(f"{indeterminate} run(s) produced no determinate outcome")
    if unfinished:
        blockers.append(f"{unfinished} paid run(s) logged as started but never finished")
    if not retried:
        # An all-clean sample is a fine reading of the *base rate* and no
        # reading at all of recovery. Exiting 0 here would let "24 runs, no
        # problems" be quoted as if the re-ask had been shown to work.
        blockers.append("no run exercised the re-ask — the recovery metric has no denominator")

    # Runs are what was spent; generations are what could have been evidence. A
    # run refused before the model is neither a success nor a failure of the
    # re-ask, and reporting only the run count states a sample larger than the
    # one that exists (Yi Xin's 2026-07-28 run found a third of it was this).
    # Three counts, because there are three states and only two of them are
    # known. An indeterminate run may or may not have reached the model, and
    # `len(rows) - no_generation` quietly asserted that it did (2026-07-28 P2).
    # A row whose two readings disagree, or which has no second reading, is
    # equally unknown — printing it under a confident heading is how a disputed
    # row becomes a quoted one. Deliberately *not* labelled "generations"
    # either: a run whose re-ask fired spent two, so this counts runs.
    def settled(row: dict) -> bool:
        return row["outcome"] not in INDETERMINATE and not row.get("disagreement") and complete(row)

    reached = sum(1 for r in rows if settled(r) and r["outcome"] != "no_generation")
    no_generation = sum(1 for r in rows if settled(r) and r["outcome"] == "no_generation")
    unknown = len(rows) - reached - no_generation
    headline = f"runs={len(rows)}  reached the model={reached}  refused before it={no_generation}"
    if unknown:
        headline += f"  unknown={unknown}"
    lines = [headline]
    lines += [f"  {name:22} {count}" for name, count in sorted(counts.items())]
    if no_generation:
        gates = ", ".join(
            sorted({str(r.get("refusal_gate")) for r in rows if r["outcome"] == "no_generation"})
        )
        lines.append(
            f"{no_generation} run(s) were refused before the model was called "
            f"(gates: {gates}) and could not have produced a contract failure"
        )
    if blockers:
        # The ratio is withheld, not merely captioned. A headline that reads
        # "recovered 1 of 1" beside a warning is the line that gets copied into
        # the review; leaving it on the screen is what makes it quotable
        # (red-team round 4 P1).
        lines.append("recovery metric withheld — see the blockers below")
    else:
        lines.append(f"re-ask fired {retried}, recovered {recovered} of {retried}")
        # Only sound when every run landed in a determinate bucket: a retry that
        # died mid-stream did observe an attempt-1 failure, and counting only
        # the determinate ones would undercount it (red-team round 5 P2).
        lines.append(
            f"attempt-1 contract failures (any class): {retried + counts.get('not_retried', 0)}"
        )

    if blockers:
        lines.append("")
        lines.append("UNQUOTABLE — the evidence has holes; do not publish a number from this run:")
        lines += [f"  - {b}" for b in blockers]
    return "\n".join(lines), not blockers


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_run_row(entry: dict, path: Path) -> None:
    """Every field `classify`/`disagrees` reads must be present *and* well typed.

    Replay recomputes the verdict from the raw fields, and `.get()` on a missing
    key returns None — which is a *value* in this classification, not an absence
    of one. A row missing `refusal_gate` would silently become a recovery
    (round 3 P1). Presence alone is not enough either: `"stream_restarts": -1`
    is truthy and would score as a re-ask that recovered (round 4 P1).
    """

    def bad(reason: str) -> None:
        raise SystemExit(
            f"{path}: run {entry.get('run')!r} {reason} — "
            "its verdict cannot be recomputed, so the log is not trustworthy"
        )

    if not _is_int(entry.get("run")) or entry["run"] < 1:
        bad("has no usable run number")
    required = [
        "saw_result",
        "stream_restarts",
        "token_events",
        "trace_llm",
        "trace_outcome",
        "trace_spans",
    ]
    if not entry.get("transport_note"):
        required += ["refusal_gate", "stream_error", "refused"]
    missing = [field for field in required if field not in entry]
    if missing:
        bad(f"is missing {', '.join(missing)}")
    if not isinstance(entry["saw_result"], bool):
        bad("has a non-boolean saw_result")
    if not _is_int(entry["stream_restarts"]) or entry["stream_restarts"] < 0:
        bad("has a stream_restarts that is not a count")
    if not _is_int(entry["token_events"]) or entry["token_events"] < 0:
        # `no_generation` turns on "the stream showed no text", so an absent
        # count would let replay read missing evidence as proof (2026-07-28 P1).
        bad("has a token_events that is not a count")
    expected_tag = QUERIES[(entry["run"] - 1) % len(QUERIES)][0]
    if entry.get("query") != expected_tag:
        bad(f"claims query {entry.get('query')!r} where the cycle assigns {expected_tag!r}")
    for field in ("refusal_gate", "stream_error", "transport_note"):
        if entry.get(field) is not None and not isinstance(entry[field], str):
            bad(f"has a non-string {field}")
    if entry.get("refused") is not None and not isinstance(entry["refused"], bool):
        bad("has a non-boolean refused")
    if entry["saw_result"] and (note := malformed_result(entry)):
        # Replay must apply the same rule the live path does, or a blank gate
        # written by some other hand replays as a coherent non-contract refusal
        # and lands in `retried_recovered` (red-team round 6 P1). Only for rows
        # that *saw* a result: a run whose stream died has no result object to
        # be malformed, and demanding one would reject the tool's own output.
        bad(note)
    spans = entry["trace_spans"]
    if spans is not None:
        if not isinstance(spans, dict) or set(spans) != {"llm", "generation"}:
            bad("has a trace_spans that is not the pair the reader writes")
        if not all(isinstance(v, bool) for v in spans.values()):
            bad("has a trace_spans whose values are not booleans")
    decision = entry["trace_outcome"]
    if (entry["trace_llm"] is None) != (decision is None) or (decision is None) != (spans is None):
        # `read_back_trace` yields both or neither; a row with one of them was
        # not written by this tool.
        bad("has parts of a second reading that do not agree on existing")
    if decision is not None:
        if not isinstance(decision, dict) or not isinstance(decision.get("refused"), bool):
            bad("has a trace_outcome that records no readable decision")
        if decision.get("gate") is not None and not isinstance(decision["gate"], str):
            bad("has a trace_outcome with a non-string gate")
    trace = entry["trace_llm"]
    if trace is not None:
        if not isinstance(trace, dict):
            bad("has a trace_llm that is neither null nor an object")
        if any(field not in trace for field in TRACE_FIELDS):
            # An empty or partial dict would pass the cross-check as agreement
            # while carrying no second reading at all (round 4 P3).
            bad("has a trace_llm missing the fields the second reading writes")
        for field in TRACE_FIELDS:
            value = trace[field]
            if value is not None and (not isinstance(value, str) or not value.strip()):
                # `disagrees` reads any non-None value as an event having been
                # recorded, so `false` or `""` would be affirmative evidence for
                # something that never happened (round 5 P1).
                bad(f"has a trace_llm.{field} that is neither null nor a reason")


def load_prior(path: Path) -> tuple[list[dict], int, int]:
    """Replay the log: finished rows, paid-but-unseen count, next free run number.

    Derived fields (`outcome`, `disagreement`) are recomputed from each row's
    raw observations rather than trusted as stored, so a log can never carry a
    verdict reached by logic this build no longer agrees with.
    """
    rows, started, finished = [], set(), set()
    meta = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        kind = entry.get("kind")
        if kind == "meta":
            if meta is not None or rows or started:
                # Meta must be the first record. Accepting one appended later
                # would let an old log be laundered into a current artifact by
                # tacking the current version on the end (red-team round 4 P1).
                raise SystemExit(f"{path}: misplaced or repeated meta line — not trustworthy")
            meta = entry
        elif meta is None:
            raise SystemExit(f"{path}: first record is not the version meta — not trustworthy")
        elif kind == "start":
            if not _is_int(entry.get("run")) or entry["run"] < 1:
                # `1.0` and `True` compare equal to `1` in a set, so an untyped
                # start could satisfy the start/outcome pairing for a different
                # run than the one it names (red-team round 6 P2).
                raise SystemExit(f"{path}: start row has no usable run number — not trustworthy")
            if entry["run"] in started:
                raise SystemExit(
                    f"{path}: run {entry['run']} started twice — log is not trustworthy"
                )
            expected_tag = QUERIES[(entry["run"] - 1) % len(QUERIES)][0]
            if entry.get("query") != expected_tag:
                raise SystemExit(
                    f"{path}: start {entry['run']} claims query {entry.get('query')!r} where "
                    f"the cycle assigns {expected_tag!r} — log is not trustworthy"
                )
            started.add(entry["run"])
        elif kind == "run":
            if entry["run"] in finished:
                # Two shells appending to one log, or a hand-edited file. The
                # counts would silently double; refuse rather than de-duplicate.
                raise SystemExit(
                    f"{path}: run {entry['run']} logged twice — log is not trustworthy"
                )
            if entry["run"] not in started:
                # An outcome with no matching `start` was never paid for by this
                # accounting — it is a row from somewhere else, and it must not
                # be adopted as evidence (red-team round 3 P1).
                raise SystemExit(
                    f"{path}: run {entry['run']} has an outcome but no start — "
                    "log is not trustworthy"
                )
            validate_run_row(entry, path)
            finished.add(entry["run"])
            rows.append(entry)
        else:
            raise SystemExit(f"{path}: unknown record kind {kind!r} — log is not trustworthy")

    if meta is None and not rows and not started:
        raise SystemExit(f"{path}: empty — an abandoned log; delete it or choose another --out")
    if meta is not None and meta.get("queries") != [list(q) for q in QUERIES]:
        # The sampling plan is part of the measurement. Continuing a log with a
        # different query mix would pool two plans under one number, and relying
        # on someone remembering to bump LOG_VERSION is not a guard. The exact
        # question text is compared, not just the tags: the same tag over a
        # reworded prompt is a different sample (2026-07-28 P1).
        raise SystemExit(
            f"{path}: sampled {meta.get('queries')!r}; this probe samples "
            f"{[list(q) for q in QUERIES]!r}. Start a fresh --out rather than mixing plans."
        )
    if meta is None or meta.get("version") != LOG_VERSION:
        # Rows written by an earlier build carry that build's verdicts. This
        # file has already shipped one version whose trace cross-check read the
        # wrong key and therefore agreed with everything; resuming onto such a
        # log would launder those rows into a current measurement.
        raise SystemExit(
            f"{path}: written by {meta.get('version') if meta else 'an unversioned probe'}; "
            f"this probe writes {LOG_VERSION}. Start a fresh --out rather than mixing them."
        )
    for row in rows:
        row["outcome"] = classify(row)
        row["disagreement"] = disagrees(row)
    # Allocate above every id ever *seen*, not every id finished: reusing the
    # number of a run that was paid for and never completed would overwrite the
    # only evidence that it happened.
    return rows, len(started - finished), max(started | finished, default=0) + 1


def lock_log(path: Path):
    """Take the session's exclusive lock, or return None if another probe holds it.

    A sibling ``.lock`` file rather than the log itself, because the lock has to
    be held *before* the log is read or created — locking the log after replay
    leaves a window in which two probes compute the same next run number from
    the same stale state, and each then writes a self-consistent report that
    omits the other's paid run (red-team round 3 P0).

    ``flock`` is advisory and is not honoured on every network filesystem; keep
    the log on a local disk. The duplicate/orphan checks in `load_prior` are the
    backstop, and they fail closed rather than de-duplicating.
    """
    lock_path = path.with_name(path.name + ".lock")
    try:
        handle = lock_path.open("a", encoding="utf-8")
    except OSError as exc:
        # A read-only directory or a bad permission is not "someone else holds
        # the lock"; saying so would send the operator hunting a phantom probe.
        raise SystemExit(f"cannot create the session lock {lock_path}: {exc}") from exc
    if not take_flock(handle):
        handle.close()
        return None
    return handle


def durably_write(log, record: dict) -> None:
    """Append one record and put it on the disk, not merely in the OS buffer.

    `flush()` survives this process dying; it does not survive the host dying,
    and a `start` line lost that way is a paid call the resume cannot know
    happened (red-team round 9 P2).
    """
    log.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.flush()
    os.fsync(log.fileno())


def take_flock(handle) -> bool:
    """Non-blocking exclusive lock on an open file. False if someone holds it."""
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def run_session(client, log, rows: list[dict], next_number: int, runs: int, budget: int) -> int:
    """Run up to `runs` queries, appending to `log`. Returns budget units charged."""
    charged = 0
    for _ in range(runs):
        # Reserve the worst case, not the best: a run admitted with one
        # generation left can still re-ask and spend two.
        if charged + 2 > budget:
            print(f"stopping: generation budget {budget} could not cover another run")
            break
        number = next_number
        next_number += 1
        # Cycled by run number, not by how many rows finished: a resume after a
        # killed run would otherwise repeat that run's query and leave another
        # untouched (red-team round 4 P2).
        tag, question = QUERIES[(number - 1) % len(QUERIES)]
        # Written *before* the call: a run that dies mid-generation was still
        # paid for, and a log that omits it would let a resumed sample look
        # complete when it is not.
        durably_write(log, {"kind": "start", "run": number, "query": tag})
        row = {"kind": "run", "run": number, "query": tag, **run_once(client, question)}
        row["outcome"] = classify(row)
        row["disagreement"] = disagrees(row)
        # A run whose stream could not be read may well have funded a re-ask
        # before it broke. Charging it as one generation would let the fence
        # advertise a bound the spend can exceed (red-team round 5 P2).
        seen = 1 + row["stream_restarts"]
        trace = row.get("trace_llm") or {}
        if trace.get("recovered_after_contract_failure") or trace.get("first_attempt_error"):
            # The trace says a re-ask happened even if the stream lost the
            # event. The fence must charge the higher of the two lower bounds,
            # or a dropped frame buys a free generation (2026-07-28 P2).
            seen = max(seen, 2)
        free = (
            row["outcome"] == "no_generation"
            and not row["disagreement"]
            and row.get("trace_spans") is not None
        )
        if row.get("transport_note") or row["outcome"] in INDETERMINATE:
            # A stream that simply stopped has no `transport_note`, but the call
            # may already have funded a re-ask. Anything indeterminate charges
            # the worst case: the fence may over-state spend, never under-state
            # it (2026-07-28 P2).
            charged += max(2, seen)
        elif free:
            # Refused at the threshold gate, and the trace confirms no model
            # span was ever written — so nothing was billed. The stream's word
            # alone is not enough: the spend path must not trust a reading the
            # metric path would have rejected (red-team 2026-07-28 P1).
            charged += 0
        else:
            charged += seen
        rows.append(row)
        durably_write(log, row)  # ^C after this leaves the run as evidence
        print(
            f"run {row['run']:<4} {tag:11} {row['outcome']:22} "
            f"token_events={row['token_events']:<5} trace={row['trace_id']}"
            + ("  !! stream/trace disagree" if row["disagreement"] else ""),
            flush=True,
        )
        if charged > budget:
            # Only reachable when the endpoint re-asked more than the once this
            # fence reserves for. Say so rather than let the advertised bound
            # quietly become untrue (red-team round 4 P2).
            print(f"!! budget violated: {charged} charged against a cap of {budget}; stopping")
            break
    return charged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=12, help="queries this session (default 12)")
    parser.add_argument("--out", type=Path, required=True, help="JSONL log, append-only")
    parser.add_argument("--resume", action="store_true", help="append to an existing --out")
    parser.add_argument(
        "--max-generations",
        type=int,
        default=None,
        help="hard stop once this many paid generations are charged this session "
        "(default: 2 × --runs, the worst case when every run re-asks)",
    )
    args = parser.parse_args()
    if args.runs < 0:
        parser.error("--runs cannot be negative")
    if args.max_generations is not None and args.max_generations < 0:
        parser.error("--max-generations cannot be negative")

    budget = args.max_generations if args.max_generations is not None else 2 * args.runs
    if args.runs > 0 and budget < 2:
        # A budget that cannot admit even one worst-case run would run nothing
        # and then exit on the strength of whatever was already in the log.
        print(f"--max-generations {budget} cannot cover a single run (worst case 2); nothing to do")
        return 2

    # Canonical path before locking: two symlinks to one log would otherwise get
    # two different sibling locks, and each session would append to the same
    # artifact while reporting only its own runs (red-team round 4 P1).
    args.out = args.out.resolve()
    if args.resume and not args.out.exists():
        # Checked before the mkdir below, so a typo'd resume path does not leave
        # a directory behind on its way out (red-team round 5 P3).
        print(f"{args.out} does not exist; --resume has nothing to continue")
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_log(args.out)
    if lock is None:
        print(f"{args.out} is locked by another probe; wait for it or choose another --out")
        return 2

    with lock:
        prior: list[dict] = []
        unfinished = 0
        next_number = 1
        if args.out.exists():
            if not args.resume:
                print(f"{args.out} exists; pass --resume to add to it, or choose another --out")
                return 2
            log = args.out.open("a", encoding="utf-8")
            # Lock the log's own inode before replaying it. The sibling lock is
            # keyed by pathname, so a *hard link* to the same log gets a
            # different sibling and would sail past it (red-team round 5 P0).
            if not take_flock(log):
                log.close()
                print(f"{args.out} is locked by another probe (via another name)")
                return 2
            prior, unfinished, next_number = load_prior(args.out)
        else:
            log = args.out.open("x", encoding="utf-8")
            # The inode lock matters here too, and for the same reason as on the
            # resume path: a hard link to this brand-new log gets a different
            # sibling lock, and only the inode is common to both names. Taken
            # before the meta line, so nothing is written unlocked (round 6 P0).
            if not take_flock(log):  # pragma: no cover - we just created it
                log.close()
                print(f"{args.out} is locked by another probe (via another name)")
                return 2
            durably_write(
                log,
                {"kind": "meta", "version": LOG_VERSION, "queries": [list(q) for q in QUERIES]},
            )

        print(
            f"session: {args.runs} run(s); {len(prior)} already logged, "
            f"total will be {len(prior) + args.runs}\n"
            f"worst case this session: {2 * args.runs} paid answer generations "
            f"(one per run, two when the re-ask fires); hard stop at {budget}\n"
            "this bound covers answer generations only — a figure refusal can "
            "also spend VLM second-look calls the fence does not count"
        )
        if unfinished:
            print(f"note: {unfinished} earlier run(s) were paid for but never logged an outcome")

        rows = list(prior)
        with log:
            # `raise_server_exceptions=False` so an app-side crash comes back as
            # a 500 this probe can record, rather than a traceback that discards
            # the session (red-team round 4 P2).
            client = TestClient(app, raise_server_exceptions=False)
            charged = run_session(client, log, rows, next_number, args.runs, budget)

        report, quotable = tally(rows, unfinished)
        print("\n" + report)
        # "Charged", not "spent": this counts budget units the fence reserved,
        # derived from the restart events seen. It is not a reading of the
        # provider's own usage counter, and must not be quoted as one.
        print(f"\nbudget units charged this session: {charged}")
        print(f"log: {args.out}")
        return 0 if quotable else 1


if __name__ == "__main__":
    raise SystemExit(main())
