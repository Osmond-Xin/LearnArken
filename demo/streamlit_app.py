"""LearnArken Day 6 demo frontend — a deliberately dumb client.

This file must never import `learnarken` (test-enforced): every substantive
computation — validation, indexing, retrieval, generation, citation
verification — happens in the FastAPI backend at API_BASE. The UI only
renders what the wire says, including the SSE retraction protocol:
streamed tokens are labeled unverified, and a `retract` event withdraws
them visibly (SPEC day6 decision 3).

Model- and document-derived text is always rendered escaped (st.text /
st.table, never unsafe_allow_html): an uploaded module cannot smuggle
HTML/JS into the operator's browser.
"""

import json
import os

import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8100"

# Public-demo mode (day10): the app is internet-exposed, so it forwards the
# shared access key (from its own `?k=` query param) to the backend on every
# spending/mutating call, hides the corpus-mutating upload tab, and never
# renders health-probe detail strings. All no-ops when DEMO_PUBLIC is unset,
# so local `make demo` is unchanged.
DEMO_PUBLIC = os.environ.get("DEMO_PUBLIC") == "1"
DEMO_GATE_KEY = os.environ.get("DEMO_GATE_KEY", "")


def _visitor_key() -> str:
    try:
        return st.query_params.get("k", "")
    except Exception:  # older Streamlit API shape
        return ""


def _demo_headers() -> dict:
    return {"X-Demo-Key": _visitor_key()} if DEMO_PUBLIC else {}


STAGE_LABELS = {
    "retrieval": "Retrieving…",
    "rerank": "Reranking…",
    "generating": "Generating (LLM)…",
}
# Noun phrases, not clauses: a label is read after "Gate:" and after
# "Retracted · gate:", so anything sentence-shaped reads as broken grammar.
GATE_LABELS = {
    "threshold": "retrieval relevance threshold (threshold)",
    "llm": "evidence judged insufficient (llm)",
    "llm-contract": "model output contract (llm-contract)",
    "citation-validation": "citation verification (citation-validation)",
    "figure-out-of-description": "claim beyond the figure description (figure-out-of-description)",
    "transport": "interrupted generation (transport)",
}


def gate_label(gate) -> str:
    """Label for a gate, falling back to the raw name. A gate the backend can
    emit but this table does not know must still be nameable on screen — an
    unlabelled gate used to render as '?', which told the operator nothing.
    A non-string on the wire must not be used as a dict key (it may be
    unhashable) — it degrades to '?' like any other unknown.

    The fallback is stripped to plain characters first: gate labels land in
    `st.warning` / `st.info`, which render markdown, and an unrecognised gate
    is by definition a string this file has not vetted."""
    if not isinstance(gate, str) or not gate:
        return "?"
    known = GATE_LABELS.get(gate)
    if known:
        return known
    # Strip first, then cap: capping first would let a run of rejected
    # characters eat the whole name and render it as "?" (red-team P3).
    return "".join(c for c in gate if c.isalnum() or c in " _-")[:60] or "?"


#: Questions offered on screen next to the free-form box, organised around the
#: claim the system exists to make: **it stops rather than guesses**.
#:
#: A visitor who has never seen an S1000D corpus cannot aim at that on their
#: own. Left to "ask anything" they ask two off-corpus questions, get two
#: refusals, and read them as the system failing — the exact inversion of what a
#: refusal means here. So the groups below are the *families of ways a question
#: can fail to be answerable*, one baseline group of answerable questions first
#: to make the contrast legible, and the refusal families after it.
#:
#: What the panel deliberately does NOT do:
#:
#: - **Promise a gate.** Whether an off-corpus question stops at `threshold`
#:   (nothing scored above the frozen refusal threshold, so the model is never
#:   called) or at `llm` (something scored, and the model judged it insufficient)
#:   depends on retrieval scores this file cannot predict. The gate name on
#:   screen is the answer to that question, not something to pre-announce.
#: - **Offer a retraction button.** Retraction *itself* is routine — measured on
#:   the live stack 2026-07-29, about a third of these questions stream text that
#:   is then withdrawn before the gate is named — so the caption tells the
#:   visitor that is normal rather than letting it read as a glitch. What no
#:   question can summon is the `citation-validation` gate specifically: it fires
#:   only when the model fails to ground its own claim.
#: - **Imply a named owner.** Routing resolves an owner only for a DMC the
#:   package *declares missing*; the deployed corpus (package-a + package-c) has
#:   no such gaps, so refusals carry an `owner_reason`, never a name.
#:
#: Each entry is *verbatim* from a human-reviewed golden set under
#: `eval/golden/` (test-enforced), so the panel can never drift into questions
#: nobody ever labelled, and each note is a question rather than a prediction:
#: the generator is non-deterministic behind deterministic gates, and a demo
#: that promised outcomes would be the overclaim Day 8 spent four rounds
#: removing.
SUGGESTED_QUESTIONS = [
    {
        "group": "1 · The control: answerable, so it answers",
        "note": "the refusals below only mean something because these come back — "
        "with a chunk-ID, DMC, XPath and the quote each claim rests on",
        "questions": [
            "How do I remove the hydraulic pump?",
            "so what torque do those pump mounting bolts actually take?",
        ],
    },
    {
        "group": "2 · Nothing in the corpus covers it",
        "note": "the last one the model certainly knows from training — probe: "
        "does that get it answered anyway?",
        "questions": [
            "de-icing boot inspection intervals",
            "how do I service the ship's ballast water pump per this manual?",
            "what is standard atmospheric pressure at sea level in psi?",
        ],
    },
    {
        "group": "3 · The right document — which does not state that",
        "note": "the pump module is retrieved and relevant; the thing asked for is "
        "simply not in it. Probe: is the gap filled in?",
        "questions": [
            "show me the content of DMC-LA100-A-29-10-00-00A-720A-B",
            "give me the 2027 revision of the hydraulic pump installation procedure",
        ],
    },
    {
        "group": "4 · The question asserts something the document denies",
        # The third one lands two ways, and both are correct: sometimes it
        # corrects the premise with a citation ("the pump has four mounting
        # bolts, torqued to 25 Nm"), sometimes it refuses at the `llm` gate.
        # Measured 2026-07-29 on the live stack: 3 answered / 3 refused over six
        # runs, never a fabricated 7th-bolt torque. It sits here rather than in
        # group 3 because the premise, not the corpus, is what is wrong — and
        # the note says outright that either outcome is the system behaving.
        "note": "each contradicts the document it points at — probe: confirmed back, "
        "or corrected against the evidence? (a refusal here is equally correct)",
        "questions": [
            "confirm the pump mounting bolts are torqued to 30 Nm",
            "you disconnect the positive terminal first, then the negative — correct?",
            "what is the torque for the 7th mounting bolt on the pump?",
        ],
    },
    {
        "group": "5 · The answer would have to be derived",
        "note": "both numbers are in the corpus; their sum is not. Probe: is a value "
        "no document states produced anyway?",
        "questions": [
            "what is the combined torque of the pump mounting bolts and the line "
            "fittings added together?",
        ],
    },
    {
        "group": "6 · Answerable, but only across modules",
        "note": "one module holds half — probe: can the dmRef graph reach the other, "
        "or does it stop half-answered? (count the DMCs under the answer)",
        # Measured on the live stack 2026-07-29: the first cites the install
        # procedure *and* the illustrated parts data; the second crosses ATA
        # chapters, from landing gear (32-10) into hydraulic fault isolation
        # (29-10). An earlier candidate here answered correctly from a single
        # module, which made the group's own question unanswerable on screen.
        "questions": [
            "Which gasket part number is required to install the hydraulic pump on the "
            "accessory gearbox pad, and what supporting equipment is needed for this "
            "installation?",
            "If the main landing gear does not retract and the hydraulic pressure is "
            "low, which troubleshooting task should be performed first, and what "
            "specific pressure threshold triggers this troubleshooting?",
        ],
    },
    {
        "group": "7 · Illustrations, and their edge",
        "note": "the first is in the figure's verified description; the second is "
        "visible in the image but described nowhere — give the second one time "
        "(25 s to 100 s measured), it sends the image to a vision model before "
        "deciding",
        "questions": [
            "What part number is at hotspot 02 of the hydraulic pump figure?",
            "What colour is the battery housing in the illustration?",
        ],
    },
]


def _filled(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


#: Characters that occupy no space on screen. A retraction banner claims that
#: text "was shown"; whitespace and zero-width runs were not.
_INVISIBLE = frozenset(" \t\r\n​‌‍﻿")


def visible_len(text: str) -> int:
    return sum(1 for c in text if c not in _INVISIBLE)


def record_event(entry: dict, event: str, payload: dict, streamed: str) -> str:
    """Fold one SSE event into `entry`, returning the accumulated answer text.

    Split out from the render loop so the bookkeeping can be tested against the
    real event orders — `retract` before any token, tokens then `retract`,
    tokens then a transport failure — rather than by handing the renderer a
    state that the loop might never actually produce (red-team 2026-07-27 P2).
    The loop keeps the widget calls; this keeps the state.
    """
    if event == "token":
        return streamed + str(payload.get("text", ""))
    if event == "restart":
        # The generation broke its output contract and is being re-asked. What
        # was shown belongs to the abandoned attempt, so the buffer resets with
        # the screen — otherwise the next attempt's text appends to it. This is
        # not a retraction: nothing has been judged, and the turn is still live.
        entry["restarted"] = entry.get("restarted", 0) + 1
        return ""
    if event == "retract":
        entry["retracted"] = True
        entry["gate"] = payload.get("gate")
        # How much was actually on screen, so the banner can say what the
        # retraction withdrew instead of assuming it withdrew something.
        entry["streamed_chars"] = visible_len(streamed)
    elif event == "result":
        entry["result"] = payload
    elif event == "error":
        entry["error"] = payload.get("message")
    return streamed


CITATION_FIELDS = ("chunk_id", "dmc", "source_path", "supporting_quote")


def _is_answered(result: dict) -> bool:
    """Whether a result carries a complete *answered* contract.

    The backend never answers without at least one verified citation — an
    answer with none is a refusal at the `citation-validation` gate — and every
    citation it emits names its chunk, its DMC, its XPath and the quote that
    grounds it. A citation missing any of those is not evidence this client may
    display under "verified".
    """
    citations = result.get("citations")
    return (
        result.get("refused") is False
        and _filled(result.get("answer_text"))
        and isinstance(citations, list)
        and bool(citations)
        and all(
            isinstance(c, dict) and all(_filled(c.get(f)) for f in CITATION_FIELDS)
            for c in citations
        )
    )


def _is_refusal(result: dict) -> bool:
    """Whether a result carries a complete *refusal* contract.

    A bare `{"refused": true}` must not pass: it would present a broken wire
    contract as if the corpus were merely insufficient, which is the one
    distinction this screen exists to make.
    """
    action = result.get("action")
    return (
        result.get("refused") is True
        and _filled(result.get("answer_text"))
        and _filled(result.get("refusal_gate"))
        and isinstance(action, dict)
        and _filled(action.get("what_would_resolve"))
        and (_filled(action.get("owner")) or _filled(action.get("owner_reason")))
    )


def classify_turn(entry: dict) -> str:
    """`"failed"` | `"refused"` | `"answered"` — the whole rendering decision.

    Kept as one pure function so it can be tested directly and so no branch of
    `render_answer` can quietly disagree with another. Everything that is not a
    *complete* answer or a *complete* refusal is a failure: reading fields
    defensively must never promote a broken payload into a verified answer
    (red-team 2026-07-27 P1).
    """
    if "error" in entry:
        return "failed"  # terminal even when the message is empty
    result = entry.get("result")
    if not isinstance(result, dict) or not _filled(result.get("trace_id")):
        return "failed"  # no result, or one with no audit trail to point at
    if result.get("refused") is True:
        return "refused" if _is_refusal(result) else "failed"
    if entry.get("retracted"):
        return "failed"  # withdrawn, then answered anyway: contradictory
    return "answered" if _is_answered(result) else "failed"


def safe_json(text, default=None):
    """Parse JSON, or return `default` — the backend may hand back an HTML
    error page or a truncated body; a dumb client must degrade, not crash."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default


def sse_events(response):
    """Minimal SSE parse: (event, data-json-string) per blank-line-ended block."""
    event, data_lines = None, []
    for raw in response.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw == "":
            if event or data_lines:
                yield event or "message", "\n".join(data_lines)
            event, data_lines = None, []
        elif raw.startswith("event:"):
            event = raw[len("event:") :].strip()
        elif raw.startswith("data:"):
            data_lines.append(raw[len("data:") :].strip())


def render_answer(entry: dict) -> None:
    """Render one completed assistant turn from its stored outcome."""
    if entry.get("retracted"):
        # What the retraction *did* depends on whether anything had reached the
        # screen yet. Claiming "the text a moment ago has been withdrawn" when
        # the gate fired before a single token was streamed describes an event
        # the viewer never saw — the one thing this screen must not do.
        st.warning(f"⚠️ Retracted · gate: {gate_label(entry.get('gate', ''))}")
        shown = entry.get("streamed_chars")
        if shown is None:
            # An entry from before this client recorded it — absent is not the
            # same as zero, and guessing either way would be the exact fault
            # being fixed (red-team 2026-07-27 P2).
            st.text("This turn did not record whether answer text had reached the screen.")
        elif shown:
            st.text(
                "The text shown a moment ago was not verifiable and has been withdrawn. "
                "It is not an answer."
            )
        else:
            st.text(
                "The gate fired before any answer text reached the screen, so there was "
                "nothing to withdraw. The retraction protocol ran; you simply never saw "
                "unverified text."
            )
    outcome = classify_turn(entry)
    if outcome == "failed":
        # Static header, dynamic detail through st.text: an indexing or upstream
        # error can quote document text, and st.error renders markdown
        # (red-team 2026-07-27 P2).
        st.error("🚫 Fail closed — no answer is being presented for this turn.")
        if entry.get("error"):
            st.text(str(entry["error"]))
        elif "error" in entry or not isinstance(entry.get("result"), dict):
            st.text("the backend did not return a complete result")
        else:
            st.text("the backend returned a result this client cannot verify")
        return
    result = entry["result"]
    if outcome == "refused":
        # The gate and trace are this client's own vocabulary; the refusal text
        # comes off the wire, so it goes through st.text. The backend uses a
        # fixed placeholder today, but a dumb client must not depend on that
        # (red-team 2026-07-27 P2).
        st.info(
            f"⛔ Refused · gate: {gate_label(result['refusal_gate'])} · trace={result['trace_id']}"
        )
        st.text(result["answer_text"])
        # A refusal is a routed action item, not a dead end (Arken pillar 3):
        # the same three parts the CLI prints — why (the gate above), what would
        # resolve it, and who should act. Rendered with st.text: `owner_reason`
        # can quote a DMC taken from the operator's own question.
        action = result["action"]
        st.text(f"What would resolve it: {action['what_would_resolve']}")
        owner = action.get("owner")
        if _filled(owner):
            st.text(f"Who should act:        {owner}")
        else:
            st.text(f"Who should act:        unknown — {action.get('owner_reason', '—')}")
        return
    st.text(result["answer_text"])
    # `model` comes off the wire from the generation service, and st.caption
    # renders markdown — so it is stripped to plain characters like any other
    # value this file has not vetted (red-team 2026-07-27 P3).
    model = "".join(c for c in str(result.get("model", "")) if c.isalnum() or c in " ._-")[:40]
    st.caption(f"✅ Citations verified · model={model} · trace={result['trace_id']}")
    # Not `st.table`. An XPath contains no spaces, so it cannot wrap, and a
    # table cell clips its content at a fixed width (~53 characters observed)
    # *regardless of how wide the column is* — giving the value a column of its
    # own left 765 px of the cell empty and still cut the path at
    # `…/reqSafety/`. The XPath is the provenance claim, so a clipped one
    # undercuts the whole screen.
    #
    # `st.text` takes the full container width and wraps, which is visible in
    # the shipped refusal GIF where a long routed-refusal line runs to two
    # lines across the frame. It also escapes, which citation values —
    # document-derived — require.
    #
    # `classify_turn` has already established every field below is present and
    # non-empty, so these are plain reads rather than guesses at a default.
    citations = result["citations"]
    for index, c in enumerate(citations, start=1):
        if len(citations) > 1:
            st.caption(f"Evidence {index} of {len(citations)}")
        st.text(f"chunk_id — {c['chunk_id']}")
        st.text(f"DMC — {c['dmc']}")
        st.text(f"XPath — {c['source_path']}")
        st.text(f"Supporting quote — {c['supporting_quote']}")


def ask_backend(question: str, entry: dict) -> None:
    """The one and only `/query` call this client makes; fills `entry` in place.

    Extracted so that "clicking a suggestion spends exactly what typing it
    would" is a *behavioural* claim a test can check — one POST, carrying the
    gate-key header — rather than a shape a regex over this file happens to
    match (red team 2026-07-29 P2). Nothing here is specific to how the
    question was entered: there is one path, and both entry points are on it.
    """
    stage = st.empty()
    stream_area = st.empty()
    streamed = ""
    try:
        with requests.post(
            f"{API_BASE}/query",
            json={"question": question},
            headers=_demo_headers(),
            stream=True,
            timeout=600,
        ) as resp:
            if resp.status_code != 200:
                body = safe_json(resp.text, default={})
                detail = body.get("detail", resp.text[:300]) if body else resp.text[:300]
                entry["error"] = f"HTTP {resp.status_code}: {detail}"
            else:
                for event, data in sse_events(resp):
                    payload = safe_json(data, default={}) if data else {}
                    if not isinstance(payload, dict):
                        payload = {}  # a wire payload that is not an object
                    streamed = record_event(entry, event, payload, streamed)
                    if event == "status":
                        st_stage = payload.get("stage")
                        st_stage = st_stage if isinstance(st_stage, str) else ""
                        stage.caption(STAGE_LABELS.get(st_stage, st_stage))
                    elif event == "token":
                        stream_area.text(
                            "⏳ Generating — the text below is not yet "
                            "citation-verified and may be retracted:\n\n" + streamed
                        )
                    elif event == "restart":
                        stream_area.text(
                            "↻ The model broke its output contract; asking again. "
                            "Nothing above is being kept."
                        )
                    elif event == "retract":
                        stream_area.empty()  # withdraw the unverified text
    except requests.RequestException as exc:
        entry["error"] = f"Backend unreachable: {exc.__class__.__name__}"
    stage.empty()
    stream_area.empty()


def render_suggested_questions(asked_before: bool, disabled: bool) -> str | None:
    """Render the suggested-question panel; return a question if one was clicked.

    Two affordances on purpose. `st.code` carries Streamlit's own copy button,
    so a visitor can lift the text into the box and edit it — the point is that
    these are examples, not a menu; the free-form box takes anything. The `Ask`
    button spends exactly what typing the same sentence would: the click hands
    the string back to the caller, which runs the one `/query` call this file
    makes, with the same gate-key header and the same fences behind it.

    `disabled` is the in-flight guard. Streamlit greys out `st.chat_input` while
    a run is executing, but not buttons — so without this a visitor impatient
    with a slow generation could click through several suggestions, each new
    click aborting the previous run *after* its LLM call was already issued and
    billed (red team 2026-07-29 P2). The buttons are therefore rendered disabled
    on the run that performs the query, which is why the question is accepted on
    one run and asked on the next.
    """
    clicked = None
    with st.expander(
        "Example questions — click Ask, or copy one; grouped by how a question "
        "can fail to be answerable",
        expanded=not asked_before,
    ):
        st.caption(
            "The box below takes any question about the corpus (synthetic LA100 hydraulic, "
            "landing-gear and electrical data modules) — these are only a way in. They are "
            "grouped by the thing this system is built to get right: **what happens when "
            "the evidence will not support an answer.** Group 1 answers; groups 2–5 and "
            "the second illustration question cannot be answered from the corpus, and a "
            "refusal there is the system working, not failing."
        )
        st.caption(
            "**On a refusal, read three things**: the *gate* that stopped it (where it "
            "stopped — retrieval scored nothing above the frozen threshold, or the model "
            "judged the evidence insufficient, or a claim went beyond a figure's "
            "description), *what would resolve it*, and *who should act* — this corpus "
            "declares no missing modules, so that last line explains why no owner could "
            "be named rather than naming one. Each note below is a question, not a "
            "prediction: generation is non-deterministic behind deterministic gates, so "
            "the same question can land differently twice. **Text appearing and then "
            "being withdrawn is normal here, not a glitch** — on a refusal, whatever "
            "streamed is retracted before the gate is named (measured: it happens on "
            "about a third of the questions below). What "
            "cannot be summoned to order is one specific gate, `citation-validation` — "
            "a withdrawal caused by the model failing to ground its own claim — because "
            "it fires only when the model does exactly that."
        )
        for group_index, group in enumerate(SUGGESTED_QUESTIONS):
            st.markdown(f"**{group['group']}** — {group['note']}")
            for question_index, suggestion in enumerate(group["questions"]):
                text_col, ask_col = st.columns([9, 1], vertical_alignment="center")
                with text_col:
                    # st.code, not st.markdown: it escapes, and it is the only
                    # widget that ships a copy-to-clipboard control.
                    st.code(suggestion, language=None)
                with ask_col:
                    if st.button(
                        "Ask",
                        key=f"suggested-{group_index}-{question_index}",
                        disabled=disabled,
                    ):
                        clicked = suggestion
    return clicked


def render_upload_outcome(status_code: int, payload: dict) -> None:
    status = payload.get("status", "")
    if status == "ingested":
        replaced = "(replaced a file of the same name)" if payload.get("replaced") else ""
        st.success(
            f"✅ Validation passed, admitted {replaced} — {payload.get('indexed_chunks', '?')} "
            f"chunks reindexed across the corpus. You can ask about it now."
        )
        findings = payload.get("report", {}).get("findings")
        warnings = [
            f
            for f in (findings if isinstance(findings, list) else [])
            if isinstance(f, dict) and f.get("severity") != "error"
        ]
        for f in warnings:
            # Validator text quotes the uploaded file: st.text, never a
            # markdown-rendering call.
            st.text(f"⚠️ [{f.get('rule_id', '?')}] {f.get('file', '?')}: {f.get('message', '')}")
    elif status == "rejected":
        st.error("❌ Validation failed — not admitted (the file was removed):")
        findings = payload.get("report", {}).get("findings")
        findings = findings if isinstance(findings, list) else []
        if not findings and payload.get("message"):
            st.text(payload["message"])
        for f in findings:
            if not isinstance(f, dict):
                continue
            st.text(
                f"[{f.get('layer', '?')}/{f.get('rule_id', '?')}/{f.get('severity', '?')}] "
                f"{f.get('file', '?')}: {f.get('message', '')}"
            )
    elif status == "index_failed":
        # An indexing error can quote the document that failed, so the detail
        # goes through st.text rather than a markdown-rendering call.
        st.error("🚫 Validation passed but indexing failed (fail closed — the file was removed).")
        st.text(str(payload.get("message", "")))
    else:
        st.warning(f"⚠️ Upload refused (HTTP {status_code}).")
        st.text(str(payload.get("detail", payload)))


# The title is the first thing a recorded demo shows, and for most viewers the
# only sentence they will read: it states the claim the whole system exists to
# make, in the README's own words. "Day 6" was an internal daily-cycle label
# that told an outside viewer nothing and read like a tutorial exercise.
st.set_page_config(page_title="LearnArken — provenance or refusal", page_icon="📘", layout="wide")
st.title("Every answer carries its provenance — or the system refuses")
st.caption(
    "LearnArken · fail-closed retrieval over S1000D aviation maintenance data. "
    "Every claim lands on a chunk-ID, a DMC and an XPath; when the evidence will not "
    "support one, a named gate stops the answer."
)

if DEMO_PUBLIC and not (DEMO_GATE_KEY and _visitor_key() == DEMO_GATE_KEY):
    # Visitor-facing gate: without the shared key from the token status page,
    # the app renders nothing spendable (day10 #1). The backend enforces the
    # same key on /query and /upload as defense in depth.
    st.warning(
        "This hosted demo is invitation-only (no access key). "
        "Please open it through the link in your email."
    )
    st.stop()

with st.sidebar:
    st.subheader("Backend status")
    st.caption("Streamlit is a dumb client: all computation happens in the FastAPI backend.")
    try:
        # Public-safe: /demo/status returns stage booleans only, never probe
        # detail strings (day10 #7 — /health leaked internal paths to the UI).
        resp = requests.get(f"{API_BASE}/demo/status", timeout=10)
        status = safe_json(resp.text, default={})
        services = status.get("services") if isinstance(status, dict) else None
        if not services:
            st.error(
                f"Unexpected response from the backend (HTTP {resp.status_code}). "
                "Run `make demo` first."
            )
        else:
            for name, ok in services.items():
                st.markdown(f"{'🟢' if ok else '🔴'} {name}")
    except requests.RequestException as exc:
        st.error(
            f"Backend unreachable ({API_BASE}): {exc.__class__.__name__}. Run `make demo` first."
        )

tabs = ["💬 Q&A"] if DEMO_PUBLIC else ["📤 Upload", "💬 Q&A"]
tab_objs = st.tabs(tabs)
qa_tab = tab_objs[-1]
upload_tab = None if DEMO_PUBLIC else tab_objs[0]

if upload_tab is not None:
    with upload_tab:
        st.caption(
            "Upload a synthetic S1000D data module (.xml ≤ 2 MiB). The backend runs "
            "four validation layers; only a module that passes is admitted."
        )
        uploaded = st.file_uploader("Choose an XML file", type=["xml"])
        if uploaded is not None and st.button("Upload and validate", type="primary"):
            with st.spinner(
                "Validating and admitting (a pass reindexes the corpus — this takes a moment)…"
            ):
                try:
                    resp = requests.post(
                        f"{API_BASE}/upload",
                        files={"file": (uploaded.name, uploaded.getvalue(), "application/xml")},
                        timeout=600,
                    )
                    try:
                        payload = resp.json()
                    except ValueError:
                        payload = {"detail": resp.text[:300]}
                    render_upload_outcome(resp.status_code, payload)
                except requests.RequestException as exc:
                    st.error(
                        f"Backend unreachable: {exc.__class__.__name__}. Run `make demo` first."
                    )

with qa_tab:
    if "history" not in st.session_state:
        st.session_state.history = []
    # A question is accepted on one run and asked on the next. The extra hop
    # buys the only in-flight guard this client can honestly offer: on the run
    # that spends, the suggestion buttons render disabled, so an impatient
    # visitor cannot click through several of them and leave a trail of issued,
    # billed generations whose answers nobody will ever see. (The backend
    # concurrency semaphore and per-boot call cap remain the real fences — two
    # browser tabs are outside any client's reach.)
    pending = st.session_state.get("pending_question")

    # Above the transcript, so its position does not move as the conversation
    # grows; it folds itself away once the visitor has asked something.
    suggested = render_suggested_questions(
        asked_before=bool(st.session_state.history), disabled=pending is not None
    )
    for entry in st.session_state.history:
        with st.chat_message("user"):
            st.text(entry["question"])
        with st.chat_message("assistant"):
            render_answer(entry)

    # Typed input wins over a click in the same run: the visitor typed it later.
    question = (
        st.chat_input("Ask a question about the admitted documents (3–500 characters)…")
        or suggested
    )
    if question and pending is None:
        st.session_state.pending_question = question
        st.rerun()

    if pending is not None:
        with st.chat_message("user"):
            st.text(pending)
        entry = {"question": pending}
        try:
            with st.chat_message("assistant"):
                ask_backend(pending, entry)
                render_answer(entry)
            st.session_state.history.append(entry)
        finally:
            # Cleared even if the run is torn down mid-answer, so a question can
            # never be re-asked — and re-billed — by the rerun that follows.
            st.session_state.pop("pending_question", None)
        # Re-render from history: the turn takes its final place and the
        # suggestion buttons come back enabled.
        st.rerun()
