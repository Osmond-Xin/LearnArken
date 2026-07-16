# Day 4a failure analysis — MiniMax `embo-01` length bias inverts relevance

> **AI-generated** (Claude, implementer), 2026-07-16. Measured, reproducible;
> awaiting Yi Xin's ruling on what to do about it (see "Decision needed").
> Reproduce: `uv run python tools/probe_length_bias.py`

## Summary

The dense path is wired correctly — Vespa's ranking reproduces Python's
ground-truth cosine ordering exactly. But the **embedding model itself has a
length bias strong enough to invert relevance ranking on this corpus**: an
irrelevant short chunk out-scores the correct longer chunk for the same query.

This is not the "dense loses to BM25 on identifiers" effect the execution plan
predicted. It is broader and more damaging: dense loses on *ordinary
procedural* queries, because chunk length dominates chunk relevance.

## Evidence

### 1. The plumbing is correct (ruled out first)

| | top-1 | top-2 | top-3 |
| --- | --- | --- | --- |
| Python ground-truth cosine | closeRqmts (0.5235) | isolationStep[1] (0.5193) | proceduralStep[1] (0.5131) |
| Vespa `closeness` | closeRqmts (0.6773) | isolationStep[1] (0.6754) | proceduralStep[1] (0.6725) |

Identical ordering. Vespa's `closeness` is a monotonic transform of cosine, so
the score gap is expected. **No bug in the store, the feed, or the schema.**

Batch alignment was also ruled out: `cos(embed([t])[0], embed(all_35)[13])`
= 1.000000 — the model is deterministic per `(text, type)` and batching
preserves order.

### 2. The model discriminates fine on short English text

| cosine | pair |
| --- | --- |
| 0.7583 | "How do I remove the pump?" ↔ "Remove the four mounting bolts and remove the pump." |
| 0.6185 | "The cat sat on the mat." ↔ "A feline rested on the rug." |
| 0.2545 | "How do I remove the pump?" ↔ "The battery tray is clean." |
| 0.2111 | "The cat sat on the mat." ↔ "Hydraulic pressure is 3000 psi." |

So the model is not broken and English is not the problem. Paraphrase works:
"how do I take the pump off" ↔ the short text scores **0.6121** — the model
handles the synonym fine.

### 3. Length, not meaning, drives the collapse

Query held constant at "How do I remove the pump?":

| cosine | words | document |
| --- | --- | --- |
| **0.7583** | 9 | "Remove the four mounting bolts and remove the pump." |
| 0.5763 | 18 | the same sentence **repeated twice** — meaning identical, length doubled |
| 0.6219 | 27 | the same sentence repeated three times |
| 0.4965 | 16 | original + neutral filler ("The sky is blue. Water is wet.") |
| **0.3765** | 14 | original + five *relevant* qualifiers ("from the accessory gearbox pad") |

Duplicating a sentence cannot change its meaning, yet cosine falls 0.76 → 0.58.
Worse, adding **relevant detail** hurts more than adding irrelevant filler.

### 4. The inversion — this is the part that breaks retrieval

Query "How do I remove the pump?":

| cosine | chunk |
| --- | --- |
| 0.2903 | **the correct answer**: "Remove the four mounting bolts and remove the pump from the accessory gearbox pad. For part numbers, refer to ." |
| **0.4502** | an unrelated chunk: "All open ports are capped and the work area is clean of fluid." |

The irrelevant chunk wins by 0.16. Across the whole package-a index, the
correct chunk for that query ranks **31st of 35**.

### 5. `type=db` / `type=query` does not rescue it — and the documented convention is the *worse* one

Mean rank of the correct chunk over 4 probe queries (35 chunks; lower is better):

| index type | search type | mean rank |
| --- | --- | --- |
| db | query | 16.25 | ← the documented convention |
| db | db | 19.50 |
| query | db | 9.50 |
| **query** | **query** | **8.25** | ← best measured |

Every combination is poor, and the vendor-documented pairing (`db` for
indexing, `query` for searching) measures *worse* than ignoring the switch.
This also qualifies the 2026-07-15 probe finding: `type` does change the vector
(same text, cosine 0.860), but that asymmetry is not the win the docs imply —
and the gap is text-dependent (0.860 for one sentence, 0.561 for another).

## Why this matters for Day 4a

- The **ablation's dense row will be bad for a reason that is about the
  provider, not about dense retrieval**. Publishing "dense underperforms BM25"
  without this note would be an honest-looking but misleading conclusion —
  exactly the kind of thing the heavy red team should catch (INV-7).
- The **12 paraphrase golden queries** (drafted 2026-07-15 to demonstrate
  dense's value) will fail — but for length reasons, not semantic ones. Their
  target chunks are 1–3 sentences; the model prefers whichever chunk is
  shortest.
- **Chunking strategy is confounded with the metric**: `semantic` produces
  longer chunks (15 for package-a) than `structure` (35). Under a
  length-biased model, the chunking table would "prove" that shorter chunks
  retrieve better — a measurement artifact, not a property of the strategy.

## Decision needed (Yi Xin)

The architecture is unaffected either way: `embedding/minimax.py` is one module
behind one interface, and `vespa/store.py` never learns which model produced a
vector. Swapping providers is a single-file change.

1. **Keep MiniMax, publish the finding.** The ablation reports dense honestly
   with this note attached; the Day 4b gate then reads "the bottleneck is the
   embedding model, not the absence of SPLADE/ColBERT". Cost: the day's
   headline number is a negative result.
2. **Switch the dense path to a local BGE/E5** (the execution plan's original
   line before the 2026-07-15 MiniMax decision). Cost: reverses the
   cost-motivated decision, adds a local model dependency; benefit: the
   ablation measures retrieval instead of measuring a provider defect.
3. **Keep both**: MiniMax as the default, one local model as a second dense row
   in the ablation. Cost: a fifth row and the extra dependency; benefit: the
   length-bias claim gets a control, which is what makes it a *finding* rather
   than an anecdote.

*AI recommendation: **(3)**, if the day's budget allows — a claim this strong
("my provider's embeddings are length-biased") is worth a control row, and it
converts a negative result into the day's most defensible artifact. Fall back
to (1) if INV-8 bites.*
