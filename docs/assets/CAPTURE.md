# Demo capture runbook — Phase 0.2

> **AI-drafted** (Claude, implementer). Records Yi Xin's ruling of 2026-07-27:
> the single `demo-retraction.gif` becomes **three short GIFs**, one idea each,
> annotated with on-screen text rather than narration. First draft — written to
> be revised before the recording session, not after.
>
> The plan's standing constraint is unchanged and governs everything below:
> **one unedited take per GIF, never staged.** Retaking is allowed; making the
> system appear to do something it did not is not.

## Why three

Captions take longer to read than narration takes to hear, so one GIF covering
all three ideas would run 90–120 s — too long for a GIF and over the 5 MB
budget. Three GIFs of 15–25 s each also let the README place every one beside
the section it illustrates, and let a viewer absorb one idea at a time.

## Artifacts

| File | Shows |
| --- | --- |
| `docs/assets/demo-answer.gif` + `.trace.json` | An answer bound to its evidence |
| `docs/assets/demo-refusal.gif` + `.trace.json` | A refusal that costs nothing |
| `docs/assets/demo-retraction.gif` + `.trace.json` | A retraction, and where the refusal is routed |

Each GIF ships with **the trace of the run inside it** (red-team F-19): the
GIF is the only artifact with no reproduction path, so the trace is what makes
it checkable.

## Getting the trace of the take you kept

**The id is on screen, inside the recording.** That is deliberate — it is what
ties the GIF to its evidence. The UI prints it on both outcomes:

- answered → `✅ Citations verified · model=MiniMax-M3 · trace=20260727T172528-d9f28528`
- refused → `⛔ Refused: … Gate: … · trace=20260727T172541-3da6dab5`

**The file is on disk**, written by the backend to `eval/traces/<trace_id>.json`
(git-ignored, so nothing enters the repo on its own). `make demo` runs the
backend from the repo root, so the path is `<repo>/eval/traces/`.

Read the id off the recording — not off the directory listing — and copy that
one:

```bash
cp eval/traces/20260727T172528-d9f28528.json docs/assets/demo-answer.trace.json
```

**Do not reach for the newest file.** A recording session is mostly retakes;
the most recent trace is the last run, which is usually not the take you kept.
The id visible in the frame is the only thing that identifies the right one.

Check the copy before moving on — it prints the question and the outcome, which
you can compare against what the GIF actually shows:

```bash
uv run python -c "
import json,sys
d=json.load(open(sys.argv[1]))
o=d.get('outcome',{})
print('trace_id :', d['trace_id'])
print('question :', d['question'])
print('outcome  :', 'REFUSED at ' + str(o.get('gate')) if o.get('refused') else 'ANSWERED')
print('citations:', len(o.get('citations') or []))
print('tokens   : streamed text appears in the trace only when generation ran')
" docs/assets/demo-answer.trace.json
```

Fields the caption plans below refer to:

| Path | Holds |
| --- | --- |
| `outcome.refused` | whether this run answered |
| `outcome.gate` | which fail-closed gate fired (refusals) |
| `outcome.action` | the routed refusal: what would resolve it, who should act |
| `outcome.citations` | every citation: `chunk_id`, `dmc`, `source_path`, `supporting_quote` |
| `authorisation`, `sources_excluded` | what was withheld, and why |
| `rerank`, `retrieval` | scores behind the threshold decision |

One way to end up with an id and no file: `LEARNARKEN_TRACE_DISABLED=1`, which
the public demo sets so a visitor's question is never persisted. Local
`make demo` does not set it.

## Shared setup (once, before any recording)

```bash
# 1. Services
docker start learnarken-vespa learnarken-neo4j
until [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ApplicationStatus)" = "200" ]; do sleep 5; done

# 2. Index self-check — fails closed and tells you what to do if the corpus moved
uv run learnarken query "hydraulic pump" >/dev/null && echo "index OK"
#    On "manifest schema digest ... != current":
#    uv run learnarken index samples/package-a samples/package-c

# 3. Demo
make demo          # FastAPI :8100 + Streamlit :8501; Ctrl-C stops both
```

**Warm the models before recording.** Ask one throwaway question and let it
finish. The reranker and embedding models are per-process resident, so the
first query of a session spends ~30 s loading them — real, but not what any of
these three GIFs is about. A caption must therefore never claim anything about
cold-start latency.

**Legibility.** GIF quantises to 256 colours per frame; small text turns to
mush. Set the browser to 125–150 % zoom and record a tight region around the
chat column only — not the whole desktop. Captions go on a solid bar, sans
serif, no smaller than ~22 px at final size.

**Pacing.** A caption appears about 1 s *before* the thing it describes, so the
viewer knows where to look, and stays long enough to read twice.

---

## GIF 1 — `demo-answer.gif`

**Title: Every sentence lands on an XPath**

**What it must show.** The answer, then the evidence table underneath it:
`chunk_id`, `DMC`, `XPath`, and the verbatim `Supporting quote` that grounds
the claim — plus the trace id in the caption line. The point is not that the
system answered; it is that the answer and its evidence are the same object.

**Query, verbatim:**

```
What safety precautions apply before removing the hydraulic pump?
```

**Measured**: answered 3/3 on this build (2026-07-27, `samples/package-{a,c}`).

**Steps**

1. Warm-up query done, chat cleared (reload the page).
2. Start the recording, then paste the query and press enter.
3. Let the status line run through `Retrieving… → Reranking… → Generating (LLM)…`
   without cutting — the stages are part of the point.
4. Stop about 2 s after the citation table has fully rendered.
5. Note the `trace=` id from the caption line → copy that trace file.

**Caption plan (draft)**

| When | Text | Backed by |
| --- | --- | --- |
| before the answer streams | `Streaming — not yet verified` | the UI's own streaming banner |
| as the table appears | `Every claim → chunk, DMC, XPath, verbatim quote` | `trace.outcome.citations` |
| hold at the end | `Nothing is asserted that the source does not say` | citation gate passed |

---

## GIF 2 — `demo-refusal.gif`

**Title: Refused before the model was ever called**

**What it must show.** An off-corpus question refused at the retrieval
threshold — **instantly**, with no `Generating (LLM)…` stage, because nothing
scored above the measured threshold. Then the routed refusal underneath: what
would resolve it, who should act.

**Query, verbatim:**

```
How do I replace the coffee maker in the galley?
```

**Measured**: refused at `threshold` 3/3 on this build, sub-second, no LLM call.

**Steps**

1. Clear the chat (reload).
2. Start recording, paste, enter.
3. This one is *fast* — the whole event is under a second, so hold the recording
   about 4 s afterwards to give the captions room. Do not slow the footage down
   without labelling it.
4. Note the trace id → copy the trace file.

**Caption plan (draft)**

| When | Text | Backed by |
| --- | --- | --- |
| on the refusal | `No LLM call. Nothing scored above the threshold.` | `trace.outcome.gate = "threshold"`, no `llm` span |
| as the routing shows | `Not a dead end — what fixes it, who owns it` | `trace.outcome.action` |

The absence of a `Generating (LLM)…` stage is the whole shot. If a caption
covers that line, move the caption.

---

## GIF 3 — `demo-retraction.gif`

**Title: Withdrawn, then routed**

**What it must show.** The retraction protocol firing, and the three-part
refusal that follows.

**Query, verbatim:**

```
APU automatic start sequence
```

**Measured**: `status ×3 → retract → refused at the llm gate`, 3/3 on this
build, **`token: 0`**.

### What the screen now says by itself

On this query the model judges the evidence insufficient *before* emitting any
answer text, so the retraction event fires but **no visible text is withdrawn**.
The UI says so on its own — it branches on how much had actually reached the
screen:

```
⚠️ Retracted · gate: evidence judged insufficient (llm)
The gate fired before any answer text reached the screen, so there was nothing
to withdraw. The retraction protocol ran; you simply never saw unverified text.

⛔ Refused · gate: evidence judged insufficient (llm) · trace=…
I don't know — no answer was found in the indexed corpus.
What would resolve it: …
Who should act:        unknown — …
```

That is a better shot than a dramatic one: the screen distinguishes *the
protocol ran* from *text was withdrawn*, which is the distinction most demos
blur. Captions therefore have almost nothing left to add — do not re-narrate
what the banner already states, and never write "watch the text disappear" over
a run where nothing did.

**Caption plan (draft)**

| When | Text | Backed by |
| --- | --- | --- |
| at the retract banner | `The retraction protocol fired — before any text was shown` | `streamed_chars == 0`; no `token` events in the run |
| on the routed refusal | `Why · what would resolve it · who should act` | `trace.outcome.action` |

**Steps** — same as GIF 1, but stop after the routed refusal lines render.

### Optional better take, if it turns up

A run where text streams and is *then* withdrawn is stronger, and two questions
have produced it:

```
What does every hydraulic module in this manual have in common?
What is the complete end-to-end workflow from diagnosing low hydraulic pressure to replacing the pump?
```

- The first has produced the **`citation-validation`** gate — the model wrote an
  answer it could not ground, and the citation gate voided it. That is the best
  possible version of this GIF. Measured 3/18 runs on an earlier build; **not
  observed in 6 runs on the current build**, so treat it as a lottery ticket.
- The second produced `llm-contract` with 17 visible tokens withdrawn, 1/2 runs.
  Usable, but the gate means the model broke its output contract — the caption
  has to say that, and "infrastructure fault" is a weaker story than "the
  citation gate caught it".

Budget a fixed number of attempts (say 10) before falling back to the `APU`
take. **Retaking is fine; captioning a `llm-contract` run as a citation failure
is not.**

---

## After recording

1. Copy each trace: `cp eval/traces/<trace_id>.json docs/assets/demo-<name>.trace.json`
2. Write the captions into `docs/assets/demo-captions.md` with, per line, the
   timestamp, the text, and the trace field that backs it.
3. Burn them in with `tools/make_demo_gif.sh` (to be written) so the annotation
   step is reproducible from source recording + caption file, even though the
   recording itself is a one-off.
4. Add all three to the README **in the same commit as the image links** —
   `tests/test_readme_guards.py` asserts every relative link resolves, so a
   link committed ahead of its file fails CI.
5. Keep each GIF under 5 MB.
