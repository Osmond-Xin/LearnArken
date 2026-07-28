# Alignment audit — this repository against Arken's published architecture

> **AI-drafted, labelled** (Phase 4a of
> [docs/specs/arken-alignment-2026-07-26.md](specs/arken-alignment-2026-07-26.md)),
> reviewed by Yi Xin. Every quoted definition comes from the frozen
> [source snapshot of 2026-07-26](research/arken-source-snapshot-2026-07-26.md),
> never from a paraphrase — that rule exists because red-team finding **F-05**
> pointed out that "quotes their published definition" is worthless unless the
> definition is pinned with a date.
>
> **This is a snapshot of a live site.** It can drift. Re-fetch before relying
> on any quote here.

## What this document is

[README §6](../README.md#6-mapped-to-a-governed-reasoning-architecture) gives the
one-table version of this audit. This is the long form: for each of the seven
pillars, **their exact words**, what exists in this repository with the code and
test that settle it, and what is missing — stated in the same voice as what
works.

It is a **retrospective audit, not recovered design intent.** The thirteen daily
specs were written against this project's own
[constitution](constitution.md); not one of them cites Arken's seven properties.
The convergence where it exists is real, and where it is absent it is absent.
Claiming seven of seven would be the precise failure this architecture is built
to prevent, which is why the scoreboard below is three, one, one, one, one.

**How to check it rather than believe it.** Every row names a file or a test.
[docs/EVIDENCE.md](EVIDENCE.md) maps every claim **listed in it** → artifact →
command — which is the listed capability and benchmark claims, not every
sentence on this page;
[llms.txt](../llms.txt) is the same map for a machine — point your own agent at
it and have it check these claims against the code rather than take them from me.

| | Pillar | Verdict |
| --- | --- | --- |
| 1 | Authorisation Before Reasoning | **Partial** — query-scoped and engine-side, no identity model |
| 2 | Source-Traceable Output | **Implemented** — public demo drops trace persistence on purpose |
| 3 | Refusal as First-Class Output | **Implemented** — owner routing toy-scale |
| 4 | Gaps as Distinct Output Class | **Toy-scale** — mechanism real, their case not reachable on this corpus |
| 5 | Audit by Design | **Implemented** — with a named residual gap |
| 6 | Sovereignty by Deployment | **Enforceable & tested** — no local model bundled (README §6 uses the same label) |
| 7 | Goal-Oriented Knowledge Foundation | **Gap** — not built, and the one I agree with most |

---

## 1 · Authorisation Before Reasoning

> "Access controls operate *prior* to any reasoning step, scoping sources by
> role, region, and admission status before the model engages."
> — `/architecture`

> **"Authorization constrains reasoning, not just retrieval."**
> — `/trust`

The `/trust` sentence is the sharper one and it is the one this repo was
measured against. It settles a question a post-retrieval filter cannot: under no
reading does filtering results satisfy "constrains reasoning".

**What exists.** The clearance constraint is pushed *into the retrieval call*,
not applied to what comes back:

- the BM25 corpus is **built** without inadmissible chunks, so they are never
  scoreable — [`retrieval/__init__.py`](../src/learnarken/retrieval/__init__.py);
- the Vespa query carries the constraint **inside** its `where` clause,
  conjoined with `nearestNeighbor`, so the engine applies it during retrieval
  and the client never filters a returned row;
- graph facts injected into the prompt are redacted the same way, because a DMC
  in the prompt is reasoning too;
- exclusions are recorded in the trace with the classified DMC redacted —
  [`clearance.py`](../src/learnarken/clearance.py).

**Precisely what the tests prove**, because the difference matters here.
`test_bm25_index_is_built_only_from_admitted_chunks` proves the offline arm
outright: an inadmissible chunk never reaches the index, so it cannot be scored.
`test_clearance_lands_in_the_yql_before_nearest_neighbor` proves the predicate is
in the query with the correct closed vocabulary — **not** that Vespa evaluates it
before candidate generation internally. Whether the engine pre-filters or
post-filters an ANN search is its own execution decision and this repository does
not assert it. The claim that holds is *the constraint is part of the query, not
applied to its results*; the stronger claim would need a query-plan artifact that
is not committed here
([`tests/test_arken_alignment.py`](../tests/test_arken_alignment.py)).

An unlabelled chunk is withheld rather than assumed unclassified: fail-closed
(INV-4) applies to the gate's own malformed input.

**What is missing.** This is *scoping*, not *authentication*. There is no
identity model — a caller states its own clearance and is believed. `/trust`
describes "five disclosure levels" and "six RBAC roles"; this repository has no
counterpart to either. Nor is there the versioned knowledge-chain graph,
rollback, or the expert-approval path for corrections that the same page
describes.

**Verdict: Partial.** Calling it anything more would breach INV-7.

---

## 2 · Source-Traceable Output

> "Every answer includes a structured trace documenting sources used, sources
> excluded, review path, and current status—generated *during* reasoning, not
> retrospectively." — `/architecture`

> **Trace** — "The structured derivation record accompanying every output,
> containing question, decision, sources used/excluded, review path, and status."

**What exists.** A versioned trace per answer, written *during* the run —
[`answer/trace.py`](../src/learnarken/answer/trace.py). It carries retrieval
candidates, rerank scores against the measured threshold, the injected graph
facts, the exact LLM request, and the outcome with citations as **chunk ID ·
DMC · XPath**. Their sentence names four things; all four are present:

| Their term | Here |
| --- | --- |
| sources used | citations, each with the verbatim quote that must be findable in the cited chunk |
| sources excluded | `sources_excluded`, with score, threshold, and reason — including `authorisation` from pillar 1 |
| review path | the five spans, in order, as the answer was derived |
| current status | per-citation `status` — whether a newer issue of the cited module exists |

The model is only permitted to emit chunk ids; DMC and XPath are backfilled by
the system, so it cannot invent a plausible-looking provenance. The format is
versioned and readers accept **both** versions, because a format bump that
retro-breaks an already-published audit record is not a bump, it is a deletion.

**What is missing — one named deployment exception.** On the public demo VM,
`provision.sh` sets `LEARNARKEN_TRACE_DISABLED=1` and `write_trace` becomes a
no-op ([`answer/trace.py`](../src/learnarken/answer/trace.py)): a full trace
persists a stranger's question and the raw model output to disk, and that was
ruled a local-run feature rather than a public-demo one. So "a trace per answer"
is true of local CLI runs and of a non-public API run, and **deliberately false
of the public demo**. The
answer path still builds the same spans and runs the same gates; what is
suppressed is the persisted trace *file*, and with it the ability to audit that
run afterwards.

The demonstration traces committed beside the README's three GIFs are separately
**redacted** (prompts and raw model output removed by
[`tools/public_trace.py`](../tools/public_trace.py), which states what it strips
and why) — a publication decision, not a capability gap.

**Verdict: Implemented, with the public-demo persistence exception named.**

---

## 3 · Refusal as First-Class Output

> "When evidence cannot support a question, the system produces a structured
> refusal with reasoning, not hedging or fabrication." — `/architecture`

> **Refusal** — "A routed action item indicating why evidence is insufficient,
> what would resolve it, and who should act."

**What exists.** Strictly two outcomes, no third state (INV-4). Five refusal
gates, each naming itself in the trace so a false refusal is debuggable rather
than mysterious. Their definition has three parts and all three are built —
[`refusal.py`](../src/learnarken/refusal.py):

1. **why** — the gate that fired;
2. **what would resolve it** — registered per gate. Precisely: every gate the
   system currently emits has one and a test pins that, but the registry is a
   dict keyed by string and an unregistered gate degrades to a named
   placeholder ([`refusal.py`](../src/learnarken/refusal.py)). A convention with
   a test behind it, not a type-level contract;
3. **who should act** — from the owner map.

False-refusal and trap-refusal rates are measured, not asserted
([docs/BENCHMARKS.md](BENCHMARKS.md)) — a system that refuses everything is
equally broken and the number is the only thing that tells them apart.

**What is missing, precisely.** The owner is attached **only** when the question
names a module the corpus declares and does not contain. Inferring an owner from
free text is exactly the fabrication the refusal gate exists to prevent, so most
refusals carry an explicit `null` owner **with a reason**. On this corpus that
means owner routing routes **nothing** for refusals on this corpus; the routed
path is exercised by a synthetic gap fixture, not by live traffic. The honest
framing is that the mechanism is real and the corpus does not exercise it. The map itself is
project-authored synthetic data, not S1000D's `responsiblePartnerCompany` field,
and that is stated wherever the capability is claimed.

**Verdict: Implemented, owner routing toy-scale.**

---

## 4 · Gaps as a Distinct Output Class

> "Knowledge gaps (missing domains requiring expert contribution) are routed
> separately from refusals (questions unanswerable with current sources)."
> — `/architecture`

> **Gap** — "A detected domain where admitted knowledge is incomplete,
> requiring expert contribution." *(their wording, unemphasised; the weight this
> audit puts on "admitted" is mine.)*

**What exists.** `learnarken gaps` emits a first-class gap object on its own
surface, separate from refusals — [`gaps.py`](../src/learnarken/gaps.py). Each
carries a deterministic signature (the declared DMC, which the standard
supplies — not a generated id), the declaration path (`dmRef` or DML
registration), and an owner it routes to or an explicit unknown, never a guess.

**Where the definition refused to fit — and this is the interesting part.**
Their word is *admitted*. In this system a declared-but-absent module is an
**ingest error**, so the package carrying it is rejected at the gate and never
admitted. The two concepts meet at a stage boundary that does not exist in their
architecture. What ships is therefore two named classes:

- `pre_admission_declared_missing` — found in rejected packages;
- `admitted_declared_missing` — their case, computed over the union of admitted
  packages, and **empty on this corpus**.

Reported as empty rather than filled with the pre-admission kind. Building the
mechanism is what produced the finding, and the finding is worth more than the
feature: a fail-closed ingest gate rejects the very packages whose gaps Arken
would route. That is a genuine architectural tension between admission control
and gap detection, and it is the thing from this whole audit I would most want
to argue about with one of their engineers.

**Verdict: Toy-scale.**

---

## 5 · Audit by Design

> "The record is generated during work, making 'every action that touched
> governed knowledge' queryable and deterministic." — `/architecture`

**What exists.** Traces are generated in-operation and never reconstructed.
[docs/EVIDENCE.md](EVIDENCE.md) maps every published claim to an artifact and a
command that regenerates it. Adversarial-judge verdicts are frozen to artifacts
rather than re-run into a nicer number, and
[ADR-0004](adr/0004-measurements-are-bound-to-their-corpus.md) makes that a rule:
a benchmark is a statement about a specific corpus at a specific revision, and
when the source material changes the earlier measurement is **void, not
approximate**.

**The residual gap, stated because it is real.** CI guards dead links, the
numbers tagged in EVIDENCE.md, and every benchmark table against its source
JSON. **Hand-written prose numbers elsewhere are not machine-guarded.** The
reason this is stated rather than engineered away is that a hand-typed table
*did* drift, was caught by red team on 2026-07-25, and the response was to move
it under a generator. The same class recurred on 2026-07-28: the README's test
count drifted a fourth time and was found by re-measuring, not by CI.

**Verdict: Implemented, with a named residual gap.**

---

## 6 · Sovereignty by Deployment

> "Customer knowledge remains within governance boundaries across four
> topologies." — `/architecture`

> "Choose the perimeter; we run inside it." · "Provenance is preserved
> end-to-end; nothing leaves your perimeter without your signature." — `/deploy`

**A discrepancy worth naming.** The two public pages do not agree on the
topology set. `/architecture` lists On-Premise, Air-Gapped, Private Cloud,
Sovereign Region; `/deploy` lists Cloud SaaS, Hybrid, On-Premise, Air-Gapped.
Anything anyone says about "their four topologies" has to name which page it is
quoting. This document quotes both and assumes neither is settled.

**What exists.** Local-first by construction: embeddings (Qwen3-8B), reranking,
Vespa and Neo4j all run **on the machine**; the index and the source corpus
never leave it. Generation is OpenAI-compatible, so a loopback model server
(llama.cpp / vLLM / Ollama) is a drop-in. `LEARNARKEN_LOCAL_ONLY=1` is a **hard
egress fence** — with it armed, a non-loopback endpoint raises instead of being
called, on the chat path, the VLM path, the eval harness and the API alike
([`config.py`](../src/learnarken/config.py)).

**What is missing, plainly.** This repository bundles no local chat or VLM
model, so under the default configuration the retrieved evidence snippets and
figure bytes **do** leave the machine. The fence is the enforcement; supplying
the local model is the deployment step, and it has not been performed here. An
air-gapped run with the degradation measured is Phase 2 work and is not claimed.

**Technology note.** They run Weaviate and vLLM; this repo runs Vespa with a
local embedding/rerank stack. Different choices, same posture — worth being able
to discuss the trade-off rather than pretending convergence.

**Verdict: Enforceable and tested; no local model bundled.**

---

## 7 · Goal-Oriented Knowledge Foundation

> "Knowledge organizes around organizational work goals rather than document
> structure." — `/architecture`

> **"Conventional KM stores and retrieves. GOKM is built around the goal of the
> work — the decision being made, the procedure being executed, the answer that
> must hold up."** — `/whitepapers`

**Not built.** Knowledge here is organized by document structure — DM / DMC /
SNS — which is precisely the thing that sentence contrasts itself against.

It is also **the pillar I agree with most**, and the distance is shorter than it
looks: *the procedure being executed* is close enough to what an S1000D data
module already **is** to be uncomfortable. A goal layer — *return the aircraft
to service after a hydraulic pump replacement* as the organizing object, with
its ordered data modules, preconditions and gates — would sit above the current
structure rather than replacing it.

It is not built for a reason I can defend: a real goal taxonomy has to come from
the organization that does the work. Inventing one alone is the Step 7 failure
described in the next section, committed knowingly.

**Verdict: Gap.**

---

## 8 · The twelve-step self-audit, and what it costs me

Arken states publicly that it is built on **Goal-Oriented Knowledge Management**
(Balafas, Jackson & Dawson, Loughborough, 2004).

**I have not read that 2004 paper** — I could not obtain it. What I read is the
twelve-step knowledge-management implementation methodology from the same group
(**Dawson, 2009**), which is where the GOKM citation appears. Saying which of the
two I actually read is INV-5 applied to a bibliography.

**Why this table has seven rows and not twelve.** The repository's record names
seven of the twelve steps. The other five are not reproduced here because
writing them down from memory would be the same error as citing the 2004 paper —
a claim about a source rather than from one. Where the method is thin, the audit
is thin in the same place.

| Step | What it asks | This repository |
| --- | --- | --- |
| **1** | A *recognised* problem | **Yes.** [constitution.md §1](constitution.md), Day 1, before any code: an MRO engineer beside an aircraft, for whom a confident wrong answer is a different category of event from no answer |
| **2** | The **cost** of that problem, measured before anything is built | **No.** No costed baseline appears anywhere in this repository |
| **4** | Return on investment computed against that cost | **No.** Follows from Step 2 |
| **5** | Value to each individual who must *feed* the system | **Partial.** Every refusal is routed with what would resolve it and who should act — which is the shape of this step. But the person feeding the system was never interviewed; the routing is designed, not validated |
| **7** | Involve the users in the solution | **The origin of the whole project, and its live failure.** See below |
| **10** | The actual savings measured afterwards | **No.** Follows from Step 2 |
| **12** | Increments, each separately justified, tested and evaluated before the next | **Yes, and it is the strongest row.** Thirteen day nodes, `v0.1.0` → `v1.3.0`, plus this work package at `v1.4.0` — each with a human-written spec **decision layer**, an independent cross-host red-team review, a human adjudication, and techniques declined on evidence in [docs/adr/](adr/). The adjudications are recorded finding by finding on the later nodes; on some earlier ones they are a blanket acceptance in one line, which is a weaker artifact and is not claimed as more |

**On Step 7.** The paper argues it from a national military administration
system that shipped on time, on budget and to specification — and was received
as a disaster, because the end users were never consulted once. (The paper puts
a figure on that programme. It is not reproduced: INV-5 admits a number that can
be re-run in this repository, or no number. Being able to cite a source is not
the same as being able to reproduce it, and the argument does not need the
figure.)

That was already my instinct as a PM — the rule I worked by was that no design
starts before sitting beside the end user. What I did not have was the framework
explaining **why** it holds and what travels with it. What travels with it is
the business half: Steps 2, 4 and 10. **This repository has the engineering half
of that discipline and none of the business half.** By the standard of the
theory I am agreeing with, that is a real gap, and naming it here is cheaper
than discovering it in an interview.

And Step 7 is exactly why pillar 7 is unbuilt rather than half-built: a goal
taxonomy invented by the engineer, for users never consulted, is the failure the
step describes. Not building it is the same instinct that started the project.

---

## 9 · What I would build next, in order

Stated as a plan I can be held to, not as a roadmap:

1. **The business half.** A costed baseline for the frontline scenario (Step 2),
   the comparison Step 4 would make against it, and what Step 10 would verify —
   as *method*, with no borrowed figures. Every number in this repository is
   reproducible from it with a command, and that rule does not get an exception
   for the numbers that would flatter it.
2. **An air-gapped run, pinned first.** Model and revision, quantisation,
   runner, hardware, seed, decoding config recorded in the results — and only
   then the degradation published. An unpinned number is not published.
3. **Identity, not just scoping** — the honest next step on pillar 1, and the
   only thing that would move it off Partial.
4. **The goal layer**, if and only if there is an organization to define it
   with. Otherwise it stays a gap, correctly.

---

## 10 · The disagreements worth having

Three things in this audit I would want to argue about rather than concede:

1. **Admission control versus gap detection** (pillar 4). A fail-closed ingest
   gate rejects the packages whose gaps their definition would route. Either the
   gap class has to reach *before* admission, or admission has to admit things
   it knows are incomplete. I do not think this repository resolved it; it
   found it.
2. **Which four topologies** (pillar 6). Their own two pages disagree. That is a
   documentation question, but the answer changes what "sovereignty" is being
   claimed.
3. **Whether a retrospective audit is worth anything** (this whole document).
   My argument is that it is worth more than design intent claimed after the
   fact would be — the specs are committed and dated, and none of them mentions
   these seven properties. The convergence is checkable precisely because it was
   not planned.
