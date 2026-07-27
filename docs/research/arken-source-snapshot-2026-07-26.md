# Arken source snapshot — 2026-07-26

> **AI-generated, labelled.** Produced under Phase 0.0 of
> [docs/specs/arken-alignment-2026-07-26.md](../specs/arken-alignment-2026-07-26.md),
> in response to red-team finding **F-05**: acceptance criteria that "quote
> Arken's published definition" are worthless unless the definitions are frozen
> with a date. Every Phase 1 acceptance criterion quotes *this file*.
>
> **Access date**: 2026-07-26. Pages fetched and rendered to text; quotes below
> are as rendered. This is a snapshot of a live site — it can drift, and a
> re-fetch before any outward claim is the honest step.
>
> **Sourcing gap this file closes**: README §6 was originally drafted from
> `/architecture`, `/work` and `/about` only. `/trust`, `/deploy` and
> `/whitepapers` were never read. All three return HTTP 200 and all three carry
> material that changes the mapping.

## 1. Pages in scope

| URL | Read before 2026-07-26 | HTTP |
| --- | --- | --- |
| https://thearken.com/architecture | yes | 200 |
| https://thearken.com/work | yes | 200 |
| https://thearken.com/about | yes | 200 |
| https://thearken.com/trust | **no** | 200 |
| https://thearken.com/deploy | **no** | 200 |
| https://thearken.com/whitepapers | **no** | 200 |

## 2. The seven pillars — quoted definitions

From `/architecture`:

| # | Pillar | Quoted definition |
| --- | --- | --- |
| 1 | Authorisation Before Reasoning | "Access controls operate *prior* to any reasoning step, scoping sources by role, region, and admission status before the model engages." |
| 2 | Source-Traceable Output | "Every answer includes a structured trace documenting sources used, sources excluded, review path, and current status—generated *during* reasoning, not retrospectively." |
| 3 | Refusal as First-Class Output | "When evidence cannot support a question, the system produces a structured refusal with reasoning, not hedging or fabrication." |
| 4 | Gaps as Distinct Output Class | "Knowledge gaps (missing domains requiring expert contribution) are routed separately from refusals (questions unanswerable with current sources)." |
| 5 | Audit by Design | "The record is generated during work, making 'every action that touched governed knowledge' queryable and deterministic." |
| 6 | Sovereignty by Deployment | "Customer knowledge remains within governance boundaries across four topologies." |
| 7 | Goal-Oriented Knowledge Foundation | "Knowledge organizes around organizational work goals rather than document structure." |

Key definitions, same page:

- **Trace** — "The structured derivation record accompanying every output,
  containing question, decision, sources used/excluded, review path, and status."
- **Refusal** — "A routed action item indicating why evidence is insufficient,
  what would resolve it, and who should act."
- **Gap** — "A detected domain where admitted knowledge is incomplete, requiring
  expert contribution."
- **Sovereignty** — "Architectural commitment that customer knowledge never
  leaves their governance boundary, regardless of deployment topology."

## 3. What the three unread pages add

### 3.1 `/trust` — the sharpest statement of pillar 1

> **"Authorization constrains reasoning, not just retrieval."**

This is materially stronger than the `/architecture` wording and it settles
red-team **F-01**: a post-retrieval filter does not satisfy this sentence under
any reading. The repo's current behaviour —
[`retrieval/__init__.py:92`](../../src/learnarken/retrieval/__init__.py), "the
Vespa-backed modes retrieve first and filter after" — is the exact posture this
sentence excludes.

Also on `/trust`, none of which this repo implements:

- "Every Arken output is reviewable at five disclosure levels, every action is
  bounded by six RBAC roles, and every reasoning step is preserved for audit."
- "The full knowledge chain graph — every node from source document through
  extraction, normalization, expert enrichment, to final claim."
- "Every change is versioned with provenance; rollback to any previous state is
  supported."
- "Corrections require Domain Expert approval; every training signal is logged
  with provenance."
- A threat table rating prompt injection (High), training-signal poisoning
  (Medium), knowledge-graph corruption (High), adversarial evidence (Medium),
  model extraction (Low-Med).

**Consequence for this repo**: five disclosure levels and six RBAC roles are a
governance surface with no counterpart here. Claiming pillar 1 as anything above
"partial" would be an INV-7 breach.

### 3.2 `/deploy` — a *different* four topologies

`/architecture` lists: On-Premise, Air-Gapped, Private Cloud, Sovereign Region.
`/deploy` lists: **Cloud SaaS, Hybrid, On-Premise, Air-Gapped.** The two public
pages do not agree on the topology set. Anything this repo says about "their
four topologies" must name which page it is quoting.

- Hybrid — "Fusion Engine, Orchestrator, and Weaviate on customer hardware. UI
  and admin portal in the cloud over mTLS." Guarantee: "Data never leaves the
  customer network."
- On-Premise — "All components on customer hardware. **vLLM serves models
  locally.** Docker Compose or Kubernetes. Zero external calls."
- Air-Gapped — "On-premise with zero network connectivity. Models and knowledge
  pre-loaded. Updates via physical media only."
- "Choose the perimeter; we run inside it" · "Provenance is preserved
  end-to-end; nothing leaves your perimeter without your signature."

**Correction to an earlier assumption**: the plan's Phase 2.1 rationale leaned
on `/architecture`'s claim that the air-gapped topology "uses open-weight
models". `/deploy` does **not** say that — it says models are pre-loaded and
updated by physical media. The open-weight reading is supported by
`/architecture` only, and Phase 2.1 must cite that page specifically rather than
treat it as their settled position.

**Technology note**: they run **Weaviate** and **vLLM**. This repo runs Vespa
and a local embedding/rerank stack with an OpenAI-compatible generation
endpoint. Different choices, same posture; worth being able to discuss the
trade-off rather than pretending convergence.

### 3.3 `/whitepapers` — the GOKM primary sources, and a lead

> "Goal-Oriented Knowledge Management (GOKM) — a framework defined at
> Loughborough University in 2004 and refined through two decades of
> peer-reviewed industrial case studies."

> **"Conventional KM stores and retrieves. GOKM is built around the goal of the
> work — the decision being made, the procedure being executed, the answer that
> must hold up."**

> **"Sources, authorisations, exclusions, and gaps are first-class to the
> output, not metadata appended after the fact."**

> "refusal, exclusion, and gap travel with every answer — at the point of work";
> Arken positions itself as "the first product built to carry GOKM into
> operational workflows".

Citations given on that page:

- **Balafas, P., Jackson, T. W., & Dawson, R. J. (2004).** *A Goal-Oriented
  Approach to Knowledge Management.* Proceedings of the IRMA International
  Conference, Loughborough University.
- **Balafas, P. (2009).** Doctoral thesis extending the framework with
  operational governance constructs.

Whitepapers themselves are "available to qualified evaluators under NDA" and
"our first papers are in editorial review" — i.e. **not publicly readable**,
which independently corroborates the README's statement that the 2004 paper
could not be obtained.

**Two corrections and a lead:**

1. **Venue**: an early web-search result put the 2004 paper at ECKM Paris. The
   reference list of Dawson (2009) — the paper actually read — places it at
   **IRMA 2004, New Orleans** ("Innovations Through Information Technology",
   Idea Group), and Arken's own page also says IRMA. ECKM was wrong. The README
   cites no venue, so nothing published needs correcting.
2. **Title discrepancy**: Dawson (2009) lists it as *"Introduction of
   Goal-Oriented Knowledge Management (GOKM)"*; Arken lists *"A Goal-Oriented
   Approach to Knowledge Management"*. These may be two papers or one
   inconsistently cited. Unresolved — do not assert either title as definitive.
3. **Lead pursued and resolved — the source is obtainable.**
   **Balafas, P. (2009), *Goal-orientated knowledge management*, PhD thesis,
   Loughborough University.** Open access in the same institutional repository
   that hosts the Dawson conference paper, under the same licence:
   - Record: https://repository.lboro.ac.uk/articles/thesis/Goal-orientated_knowledge_management/9415157
   - File: `Thesis-2009-Balafas.pdf`, 7.29 MB — https://ndownloader.figshare.com/files/17034866
   - Licence: **CC BY-NC-ND 4.0** · deposited 2012-10-17
   - The title is spelled "**orientated**", not "oriented" — which is why
     searches for the framework's own name do not find it.

   From the abstract: "the majority of organisations consider KM to be
   strategically important, yet at the same time **the majority of KM
   initiatives fail**. One of the most fundamental reasons … seems to be a
   distinct lack of focus and direction … These observations provide strong
   indication of the need for goal-oriented thinking in KM. This notion is
   reinforced by lessons learnt from **a pilot KM initiative that follows
   conventional KM thinking and, ultimately, fails.**"

   **Consequence for the README**: the 2004 conference paper remains
   unobtainable, so the current sentence stays true as written. But the extended
   framework by its first author *is* readable, which means the declared theory
   gap is closeable by reading — not by rephrasing. That is a task for the
   human, not for this file. The PDF is deliberately **not committed**: CC
   BY-NC-ND permits verbatim redistribution, but the repo does not need a 7 MB
   third-party binary to make a citation.

## 4. What this snapshot changes in the plan

| Finding | Change |
| --- | --- |
| F-01 | Confirmed at maximum strength by "Authorization constrains reasoning, not just retrieval." Phase 1.4 must move clearance into BM25 corpus construction and Vespa YQL |
| F-05 | Closed by this file |
| Phase 1 framing | "Sources, authorisations, exclusions, and gaps are first-class to the output" maps 1:1 onto Phase 1.1–1.4. That sentence, not my paraphrase, is the organising quote |
| Phase 2.1 | Must cite `/architecture` specifically for the open-weight claim; `/deploy` does not support it |
| §6 sovereignty row | Must name which page's topology list it refers to |
| §6 authorisation row | Gap is wider than stated: five disclosure levels + six RBAC roles have no counterpart here |
