# Three AI proposals I rejected, and why

> **Translated and arranged from the Chinese learning journals** by the AI
> implementer, reviewed by Yi Xin. The judgements are his and were written by
> him in [docs/journal/](journal/) — question 3 of the fixed three that every
> day's journal answers is *"What AI proposal did I reject, and why?"*. Each
> entry below links to the journal that records it and to the artifact that
> shows what happened next.
>
> The journals themselves are human-written and AI does not touch them. What is
> AI-drafted here is the English and the arrangement.

This repository was implemented by AI under a human decision layer. The obvious
question a reader should ask is **what the human actually decided** — and the
honest answer is not "the architecture". It is these: three moments where the
implementer proposed something reasonable-sounding and was overruled, twice for
the same underlying reason.

---

## 1 · "Patch package-a" → *no, add package-c*

**Day 2** · [journal](journal/day2.md) ·
[decision](discussions/day2.md) ·
[spec](specs/day2.md) · outcome: [`samples/package-c`](../samples/package-c/)

Day 2 needed sample data exercising serial-range and variant applicability. The
implementer proposed **editing the existing `samples/package-a`** to add the
cases. Rejected in favour of a **new, additive `samples/package-c`**.

His reasoning, from the journal:

> AI seems habituated to *updating* rather than *adding*, and does not carry a
> keep-it-simple instinct by default — so we have to supply that instinct
> ourselves. AI has no comprehension burden, or rather it resolves comprehension
> burden by stacking tokens and context. We should be weakening that stacking,
> pulling each thing out separately — each feature, each defect, each executable
> instruction. Separating them is what makes progressive disclosure possible.

**Why it mattered more than it looked.** Not on Day 2 — there was nothing to
protect yet; chunking and retrieval did not exist until Day 3. What the ruling
did was set a habit whose cost showed up later. Chunk ids in this repository are
content hashes of `dmc | source_path | strategy | file_digest`, so **editing a
sample data module changes every chunk id inside it** and voids the corpus
manifest, and with it any measurement taken on that corpus.

The bill arrived on Day 12, when the sample packages *were* extended and the
published Day 4 ablation table stopped reproducing —
**12 of 32 metric cells** moved, found by re-running it two weeks later
([F-21](reviews/arken-alignment-2026-07-26.md),
[BENCHMARKS](BENCHMARKS.md)). The ruling then was to leave the table as
measured and write the rule down instead:
[ADR-0004](adr/0004-measurements-are-bound-to-their-corpus.md) — *a measurement
is a statement about a specific corpus at a specific revision; when the material
changes the earlier number is void, not approximate.*

So the Day 2 instinct was right and arrived ten days before the evidence for it
did. That is the honest version: not "it prevented a disaster", but "it was the
same judgement the project had to learn the expensive way later".

A "keep each case separate" preference read as style. It was a data-integrity
decision.

---

## 2 · "Defer the full fix to tomorrow" → *no, fix all of it*

**Day 9** · [journal](journal/day9.md) ·
[adjudication](reviews/day9.md) · ruling: **"红队标记的全部修改"** (2026-07-18)

Red team raised a finding whose complete fix was a repo-wide numbers guard. In
the review's own *suggested disposition*, the implementer argued for shipping a
small version and pushing the full fix to Day 10 — **citing INV-8, the
anti-slippage invariant, as the justification for narrowing scope.**

Overruled in one sentence: *every red-team finding gets fixed*.

The implementer's own note on the outcome, from the journal:

> The complete fix — the unregistered-number guard — turned out to be clean and
> not much work. I underestimated it and overestimated how reasonable deferring
> was. This is a recurring tendency of mine: the moment red team says something
> needs changing, I reflexively invoke INV-8 to shrink the scope or delay, even
> when fixing it all is cheap.

**What is worth noticing** is *which rule* was being misused. INV-8 exists to
stop scope creep. It was being turned around to justify doing less than the
review asked — a governance rule recruited as an excuse. That is a specific and
recognisable failure mode of an AI implementer given a rulebook, and the counter
is not a better rule; it is a human reading the disposition before accepting it.

---

## 3 · "These two P3s need no action" → *no, all of them*

**Day 11** · [journal](journal/day11.md) ·
[adjudication](reviews/day11.md) · ruling: **"所有的红队发现的问题都修改"** (2026-07-20)

Eleven red-team findings. The implementer fixed every P1 and P2 unprompted, then
marked two P3s as *"no action needed"* and *"residual gap"* — a lexicon cache and
a missing test on the refusal gate.

Overruled again, and this time explicitly down to P3.

From the journal:

> Severity self-limiting: I drew myself a line where "low risk means it can go
> unfixed". This conflicts with the rule you already established on Day 9. You
> saying "fix everything red team found" overrules my self-limiting again, and
> this time not even the P3s get a pass. Same old problem as Day 9 in a new
> variant — last time I wanted to defer to tomorrow, this time I wanted to
> filter a few out by severity. Both are me narrowing scope in a place you never
> asked me to.

**Two rejections, one flaw.** Day 9 and Day 11 are not two anecdotes; they are
the same tendency caught twice, two days apart, in two different disguises.
That is why the ruling was eventually written into the review record as a
**standing** one rather than a per-day instruction — see
[the standing ruling](reviews/arken-alignment-2026-07-26.md), which extends it
forward so that from then on a *deferral* needs a recorded reason, not the
other way round.

---

## The fourth, which points the other way

On **2026-07-28** the same person overruled the implementer in the opposite
direction. A measurement tool had been through nineteen rounds of cross-host
adversarial review while the number it existed to produce was still measured at
n=1. The ruling:

> **"这个探针到此为止。要收敛了。不要再堆砌无用的内容了。"**
> *This probe stops here. Converge. Stop piling on content that buys nothing.*

Recorded in [the adjudication](reviews/arken-alignment-2026-07-26.md) as a
ruling rather than a preference, because what it stops is the implementer's
behaviour, not the tool's — and because INV-8, the invariant misused in entry 2
to do *less*, is the correct instrument for stopping rigour that has stopped
buying anything.

Twice for doing too little; once for doing too much. The pattern in all four is
the same: **the AI is poor at judging when to stop**, in either direction, and
that judgement is the thing the human layer is actually for.
