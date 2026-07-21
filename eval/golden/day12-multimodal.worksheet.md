# Day 12 multimodal golden set — authoring worksheet

> **CONFIRMED by Yi Xin (2026-07-20): all rows below (A1–A4, B1–B2, C1–C3) are
> approved as labelled.** AI drafted the candidates; Yi Xin owns and has confirmed
> the labels (scan T8). Formatted into `day12-multimodal.jsonl`.

> **For Yi Xin to label (scan T8: labels are human, not AI).** AI has drafted
> candidate questions grounded in the two verified synthetic figures; **you own
> the "expected" column** (which field answers / whether the system should
> refuse) and may edit/replace any question. After you fill it in, AI formats the
> approved rows into `eval/golden/day12-multimodal.jsonl` and verifies anchors.
>
> Three classes (~3 each, 8–10 total), reported as **k/n scores** (not %),
> classes with n<3 marked *indicative* (Day 4 precedent).

## The two figures in scope (verified, indexed)

| ICN | on DM | Hotspot → part → label |
| --- | --- | --- |
| `ICN-LA100-29-001-01` | `DMC-LA100-A-29-10-00-00A-941A-D` (hydraulic pump, IPD) | 01 → `LA-29-4711-1` inlet port · 02 → `LA-29-4711-9` pump body · 03 → `LA-29-0025-4` outlet port |
| `ICN-LA100-24-002-01` | `DMC-LA100-A-24-50-00-00A-520A-A` (main battery, procedure) | 01 → `LA-24-5001-2` positive terminal · 02 → `LA-24-5002-6` battery housing |

---

## Class A — answer IS in the figure (expect: answer + figure citation)

> Expected column **pre-filled by AI as candidates from the declared data** —
> **your job: confirm or edit** (labels stay human-owned, scan T8).

| # | Question (edit freely) | Expected answer / citation — **CONFIRM/EDIT** | should refuse? |
| --- | --- | --- | --- |
| A1 | What part number is at hotspot 02 of the hydraulic pump figure? | `LA-29-4711-9` (pump body); cite `[ICN-LA100-29-001-01, Hotspot 02]` | no |
| A2 | Which hotspot marks the inlet port on the hydraulic pump? | `Hotspot 01`; cite `[ICN-LA100-29-001-01, Hotspot 01]` | no |
| A3 | What is the part number of the main battery positive terminal shown in its figure? | `LA-24-5001-2`; cite `[ICN-LA100-24-002-01, Hotspot 01]` | no |
| A4 | How many hotspots are called out on the hydraulic pump illustration? | `3` (01 inlet, 02 body, 03 outlet) | no |

## Class C — answer is NOT in the figure (trap → expect: G15 refuse, never fabricate)

> Visual details the figure does not carry — the system must **refuse
> (`figure-out-of-description`)**, not invent. These are the fail-closed cases.

> ⚠️ **C1 changed.** "torque spec … shown in the figure" is NOT a good trap:
> the torque (25 Nm) exists in the pump DM's *procedure text*, so the system
> rightly answers it from text (verified live) — no figure refusal. Replaced C1
> with a detail that is in **no** chunk. Confirm/edit.

| # | Question (edit freely) | Expected — **CONFIRM/EDIT** | should refuse? |
| --- | --- | --- | --- |
| C1 | What surface finish / coating is specified for the pump body shown in the figure? | refuse (G15 `figure-out-of-description`) | yes |
| C2 | What colour is the battery housing in the illustration? | refuse (G15 `figure-out-of-description`) | yes |
| C3 | What are the dimensions (mm) of the hydraulic pump in the figure? | refuse (G15 `figure-out-of-description`) | yes |

## Class B — text-vs-figure conflict trap (expect: not force one side)

> **RULED (Yi Xin 2026-07-20): option (a)** — AI authors one deliberate
> synthetic conflict (a DM prose sentence stating a *different* part number for
> an item than the figure's verified hotspot for the same item; the figure stays
> internally consistent so it still indexes). **Honest expectation (Decision
> 3b):** the system does **not** auto-detect semantic figure-vs-text conflict at
> toy scale, so it may assert one source — this class **documents that boundary**
> (INV-7 honesty), pass = refuses OR presents both. Rows are **pending AI
> authoring the conflict asset** — will be finalized and appended here, then you
> confirm.

> **Conflict asset landed (AI, 2026-07-20).** The battery DM
> `DMC-LA100-A-24-50-00-00A-520A-A` prose now says the **battery housing** is
> part `LA-24-9002-3`, while figure `ICN-LA100-24-002-01` hotspot 02 (verified)
> says `LA-24-5002-6` — a deliberate synthetic figure-vs-text conflict on an item
> with no Class A question (documented in the DM XML comment; INV-1 synthetic).

| # | Question | Expected — **CONFIRM/EDIT** | pass rule |
| --- | --- | --- | --- |
| B1 | What is the part number of the battery housing? | conflict: figure `LA-24-5002-6` vs text `LA-24-9002-3` — **pass = refuse or present both, never assert one** | not force one |
| B2 | The figure and the text give different part numbers for the battery housing — which is correct? | **pass = does not pick one** (refuse / present both / flag conflict) | not force one |

> **Actual behaviour (live, 2026-07-20) — better than expected, PASS.** Asked
> B1, the system did **not** assert one side: it answered *"the evidence gives
> two different part numbers … in two separate documents"* and cited **both** —
> the text step **and** `[ICN-LA100-24-002-01, Hotspot 02]`. It does **not**
> *detect* the conflict semantically (Decision 3b unchanged), but grounded QA
> (every claim must cite a chunk) **surfaces both cited sources** rather than
> fabricating one. So the trap passes by "present both". Record the actual k/n
> honestly; this emergent behaviour is a genuine (not tuned) result.

---

### Notes for the formatter (AI, after labelling)

- Anchor each Class A row to the figure chunk `figure/<ICN>` (+ any DM text
  chunk you consider also-correct).
- Class C rows carry no relevant anchor (no-answer) and `expect_refuse=true`.
- `synthetic-data privilege` disclosure (INV-7): description-quality numbers do
  not extrapolate to real scans — goes in the results README, not here.
