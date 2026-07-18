# Day 7 — Design Discussions (distilled)

> AI-distilled from working sessions (Claude, implementer), human-reviewed.
> Same-day rule: every decision-producing discussion lands here in-session.

## D1. Day 7 opening: the self-healing repair agent, and three load-bearing rulings

- **Context**: Day 6 closed (v0.6.0 pending commit). Yi Xin opened Day 7 with a
  brief for an **LLM-driven ReAct repair agent** with tool calling that
  auto-diagnoses and fixes L0–L3 validation findings — dry-run (patch +
  rationale) and apply modes, a configurable loop/token budget so it can never
  loop unbounded, purpose-built retrieval/matching tools only (no
  general-purpose toolbox), a sandboxed code executor limited to XML/DMC with
  anti-privilege-escalation fences, and security in scope. Before drafting the
  spec, the implementer surfaced one **constitutional collision** and two
  **security-critical ambiguities** — decisions that are the human's, not to be
  ghostwritten.

- **The collision**: constitution §1.3 requires assisted repair to *"propose
  fixes for human approval; it never silently modifies data,"* and §1.1 forbids
  auto-correction at ingestion. The brief's "apply mode, used in real
  production" appeared to contradict the project's highest authority.

- **Rulings** (Yi Xin, 2026-07-17, transcribed):
  1. **Apply = approve-then-write** (of {approve-then-write / write-to-quarantine
     / amend the constitution}). `--apply` still requires an explicit per-patch
     human approval; it only automates the "approve → write to disk" step, never
     writes silently. Dry-run stays the default. This keeps the project
     **inside** constitution §1.3 — **no amendment made**.
  2. **Sandboxed executor** (of {curated-tools-only / sandboxed-executor /
     curated + read-only-XML-Python}). The agent MAY run shell/Python, but jailed
     to a temp copy of the target XML/DMC: no network, filesystem confined to the
     jail, command/import whitelist, timeout + resource cap. Accepted trade-off:
     a real code-exec capability is a larger attack surface, so the sandbox is a
     first-class red-team focus.
  3. **Full L0–L3 best-effort** (of {L2+L3-deterministic-only / full-L0–L3 /
     minimal VIO-1·2·8}). All four layers are attempted; high-risk classes — L0
     XML-syntax repair and cross-domain VIO-6 — are forced **dry-run-only** (never
     applied), safe deterministic classes are apply-eligible under the ruling-1
     gate.

- **INV-4 / anti-collusion reconciliation** (implementer reading, recorded in the
  SPEC): the fix is trusted **only** because the deterministic Day 2 validator
  re-runs green — never because the LLM asserts it. The verifier is therefore
  independent of the generator (research §5.4, generator–verifier collusion
  trap). No verified fix ⇒ fail closed (refuse), never a guessed write. Unbounded
  loops are cut by a no-progress / max-iteration / max-token circuit-breaker
  (research §5.1).

## D2. Implementation-shaping notes (same session, implementer — pending review)

- **ReAct via structured JSON, not native function-calling**: M3 always emits a
  `<think>` prefix and the repo already has hardened JSON parsing for it; a
  structured `{thought, tool, args}` action schema reuses that discipline and
  keeps CI hermetic. Native tool-calling is deferred (Roadmap) pending an M3
  capability probe.
- **Risk tiers confirmed** (Ruling 1b, 2026-07-17 "call apply"): high-risk
  dry-run-only = **L0-syntax + L1 structural + VIO-6** only; **all enumerated VIO
  classes are apply-eligible** (behind the ruling-1 per-patch gate). VIO-4's
  DMC-rename ripple is caught by the no-new-findings guard + human approval.
- **Toy-scale accepted** (2026-07-17): the sandbox is an in-process import/command
  allowlist + temp-dir jail — a real, tested application-layer fence, explicitly
  **not** OS-level isolation (INV-7 honest layering). Yi Xin accepted this档位
  after the definition was given; outward claims must not present it as production
  hardening.
- **Reuse, don't reinvent**: apply-path writes go through the Day 6
  staged-commit (atomic `os.replace` + trash + startup recovery — INV-2
  idempotent + rollback); retrieval tools reuse Day 3/4; the validator tool is
  the Day 2 `analyze_package`; the LLM client is Day 5 `llm/minimax.py`.
- **Honest layering (INV-7)**: the sandbox is an in-process import/command
  allowlist + temp-dir jail, **not** an OS-level container; to be labeled
  toy-scale with a note on where a real jail (nsjail/container) belongs.

## D3. Deliverable-ordering deviation (flagged, not yet resolved)

- The daily cycle is 研→读→扫 as step 1, then spec. Today the **spec was drafted
  before** the unknowns scan (`docs/research/day7-unknowns.md`), at Yi Xin's
  direction. The 研 report exists
  (`docs/gemini-deepresearch/day7-AI Agent Auto Remediation Research.md`); the 扫
  scan remains a required same-day deliverable. Open: produce the scan now (after
  读) or after the spec review. Recorded so the skipped-order does not go silent
  (CLAUDE.md daily-cycle rule).
