# SPEC — Day 7: Self-Healing Repair Agent (ReAct + tools, `v0.7.0`)

> Decision layer **transcribed from Yi Xin's verbal instructions + three rulings**
> (2026-07-17 session). Goal and Key Decisions are [HUMAN]; Interfaces /
> Acceptance / Out-of-Scope are **AI-drafted, pending approval** (Day 6 labeling
> precedent). The three rulings resolve the load-bearing decisions surfaced
> before drafting — see Key Decisions 1/6/7. Distilled to
> [docs/discussions/day7.md](../discussions/day7.md).
>
> **Constitutional note (highest authority).** Constitution §1.3 requires assisted
> repair to *"propose fixes for human approval; it never silently modifies data,"*
> and §1.1 forbids auto-correction at ingestion. Ruling 1 (apply = approve-then-
> write) keeps this project **inside** the constitution: `--apply` never writes
> silently — it automates *"approve → commit"*, with a per-patch human gate. No
> constitution amendment is made.

## Goal (one sentence) — [HUMAN, transcribed 2026-07-17]

Ship an LLM-driven, ReAct-style repair agent with tool calling that
automatically diagnoses and proposes fixes for L0–L3 validation findings,
runs by default in **dry-run** (emitting the full patch set + rationale) and
optionally in **apply** (with a per-patch human approval gate), is bounded by a
**configurable iteration/token budget** so it can never loop unbounded, uses
**only** document-context / self-content re-retrieval-and-matching tools plus a
**sandboxed code executor jailed to the target XML/DMC** (no privilege
escalation), and closes the loop by re-running the deterministic validator —
tagged `v0.7.0`.

## Key Decisions — [HUMAN, transcribed from the 2026-07-17 instructions + rulings]

1. **`--apply` = approve-then-write (Ruling 1).** Apply mode still requires an
   explicit per-patch human approval; it only automates the "approve → write to
   disk" step. It **never** modifies data silently. Dry-run is the default mode
   (fixes are proposed, nothing is written). This satisfies constitution §1.3
   literally, with no amendment.
2. **LLM-driven ReAct loop with tool calling.** The agent reasons, acts (calls a
   tool), observes the result, and iterates — an LLM-in-the-loop closed cycle,
   not a fixed workflow.
3. **Dual mode: dry-run and apply.** Dry-run outputs the whole patch set with
   reasoning (and consulted evidence); apply is for real production use and is
   gated per decision 1.
4. **Bounded, no infinite loops.** The agent MUST NOT loop unbounded or burn
   tokens without limit; the iteration and token budgets are **configurable in a
   config file** (with CLI override).
5. **Restricted, purpose-built tools only.** No general-purpose toolbox. Tools
   are limited to: re-retrieval and matching over the document context and the
   agent's own content, and understanding thereof — plus the validator and a
   patch-proposal tool. The tools are implemented for this task, not borrowed
   whole.
6. **Sandboxed code executor (Ruling 2).** The agent MAY execute shell/Python,
   but jailed to a temporary copy of the target XML/DMC files: no network, no
   filesystem access outside the sandbox, a command/import whitelist, and a
   timeout. Anti-privilege-escalation fences are mandatory. The LLM can never
   reach the live corpus, the repo root, `.env`, or other packages.
7. **Full L0–L3 best-effort scope (Ruling 3).** All four layers are attempted.
   High-risk classes — **L0 XML-syntax repair and cross-domain VIO-6** — are
   forced **dry-run-only** (never applied, even in apply mode); safe,
   deterministic classes are apply-eligible under the decision-1 gate.
8. **Security is in scope.** The sandbox, the path/privilege fences, and the
   loop/budget circuit-breaker are part of the deliverable and go to the
   mandatory cross-host red-team gate.

- Applicable constitution rules: **§1.1 / §1.3** (never silently modify; propose
  for approval), **INV-2** (idempotent, rollback-able writes; distributed-shaped
  interfaces), **INV-3** (repairs scored only against the enumerated VIO list,
  golden pairs), **INV-4** (fail-closed: no verified fix ⇒ refuse, never guess a
  write), **INV-5** (fixed seeds, versioned fixtures, repro commands; LLM tests
  hermetic), **INV-7** (honest layering: risk tiers and toy-scale limits
  labeled), **INV-8** (2-day cap).
- The 3 concepts from today's tutorial/research to verify during implementation:
  1. **Closed-loop verification = the only trust basis** (research §3.3): the
     agent's fix is trusted **only** because the deterministic Day 2 validator
     re-runs green — not because the LLM said so.
  2. **Generator–verifier non-collusion** (research §5.4, Q2): the verifier is
     the deterministic validator, *independent of the LLM*, so the model cannot
     talk its own checker into passing.
  3. **Infinite-loop / semantic-drift defense** (research §5.1/§5.2, Q3): a
     no-progress circuit-breaker (the finding set must strictly shrink) plus a
     minimal-diff / no-new-findings guard against over-repair.

## Interfaces — [AI-drafted, pending approval]

### CLI: `learnarken repair`

```
learnarken repair <package_dir> [--apply] [--only RULE_OR_LAYER,...]
    [--max-iterations N] [--max-tokens N] [--report PATH] [--seed N]
```

- **Default is dry-run** (no `--apply`): the agent works entirely on a sandbox
  copy, writes nothing to `package_dir`, and emits a `RepairReport` (patch set +
  rationale + evidence + validator delta) to stdout and `--report` (default
  `eval/repairs/<package>-<seed>.json`, git-ignored — auditable artifact).
- `--apply`: for each **apply-eligible** patch, the proposed unified diff +
  rationale + validator delta are shown and the human is prompted
  `apply this patch? [y/N]`; on `y` the file is written via the Day 6
  staged-commit path (atomic `os.replace`, trash + startup recovery — INV-2
  idempotent + rollback). High-risk-tier patches are **shown but not offered**
  ("dry-run-only — human decision required"). Declining leaves the corpus
  untouched.
- `--only`: restrict to specific rule IDs / VIO classes / layers (e.g.
  `--only VIO-1,VIO-3` or `--only L3`).
- `--max-iterations` / `--max-tokens`: override the config-file budget.
- Exit codes (mirror the CLI INV-4 convention): `0` all targeted findings
  resolved (or in dry-run, patched-and-verified); `3` some findings had no
  verified fix (refused, fail-closed — never a guess written); `1` service /
  transport / budget-exhausted failure; `2` non-package input.

### Config file (Decision 4): `[tool.learnarken.repair]` in `pyproject.toml`

Versioned so budgets are reproducible (INV-5); CLI flags override.

```toml
[tool.learnarken.repair]
max_iterations       = 12      # per finding, hard cap on ReAct steps
max_tokens           = 60000   # cumulative LLM tokens per finding; circuit-breaker
no_progress_limit    = 3       # abort a finding if the validator delta doesn't
                               # strictly shrink for this many consecutive steps
sandbox_timeout_s    = 10      # per exec_sandbox call
sandbox_mem_mb       = 256
allowed_python_imports = ["lxml", "defusedxml", "re", "json", "pathlib"]
shell_whitelist        = ["xmllint", "cat", "grep", "head", "wc"]
# risk tiers (see below) — AI-drafted default, pending approval
```

### The ReAct loop

Driven by `llm/minimax.py` (MiniMax-M3, reused). Because M3 always emits a
`<think>…</think>` prefix and the project already has hardened JSON parsing for
it, actions are **structured JSON** (thought / tool / args), not native
function-calling — each step:

1. Prompt carries: the target finding (rule_id, layer, file, line, path,
   message, fix_hint), the tool contracts, and the running observation history.
2. Model emits one action `{"thought": ..., "tool": ..., "args": {...}}`
   (contract-violation ⇒ counts as a failed step, not a crash).
3. The tool runs (in the sandbox); its result is appended as an observation.
4. Loop until the model emits `propose_patch` **and** the follow-up
   `run_validator` shows the finding cleared with **zero new findings**, or a
   budget/no-progress limit trips (⇒ that finding is refused, INV-4).

### Tools (Decision 5 — restricted; all sandbox-scoped)

| Tool | Contract | Notes |
| --- | --- | --- |
| `search_corpus(query, k)` | BM25/hybrid retrieval over the corpus (reuse Day 3/4) → chunk snippets | "二次检索/匹配" — find how sibling modules encode the correct pattern |
| `read_module(dmc_or_file)` | return a data module's text | the agent's own-content re-read |
| `query_xml(file, xpath)` | read-only lxml XPath eval on the sandbox copy | structure understanding; cannot write/network |
| `run_validator(package)` | re-run `analyze_package` → `ValidationReport` | **closed-loop verifier — deterministic, LLM-independent (anti-collusion)** |
| `propose_patch(file, xpath, new_xml)` | stage a minimal edit into the sandbox copy; returns the unified diff | the **only** write path; bounded to the anchored node |
| `exec_sandbox(kind, code)` | run `python`/`shell` (kind) jailed to the sandbox | Decision 6 fences below |

### Sandbox & anti-escalation fences (Decision 6/8)

- **Jail root** = a per-run temp dir holding **only** copies of `package_dir`'s
  `*.xml` (+ `icn/`). Nothing else is reachable.
- **Filesystem**: every path arg is resolved and asserted to be inside the jail
  root (path-traversal / `..` rejected, Day 6 re-derivation posture); the live
  corpus, repo root, `.env`, and other packages are unreachable.
- **Network**: disabled inside `exec_sandbox` (no sockets).
- **Code**: `python` restricted to `allowed_python_imports` (denylist
  `os.system`, `subprocess`, `socket`, `open` outside jail); `shell` restricted
  to `shell_whitelist`; both under `sandbox_timeout_s` + `sandbox_mem_mb`
  (resource circuit-breaker).
- **Write barrier**: the agent can never write the active corpus. `propose_patch`
  writes the sandbox copy only; promotion to active happens **exclusively** via
  the decision-1 human-approved staged-commit.

### Risk tiers (Ruling 1b, 2026-07-17: high-risk = only L0-syntax + VIO-6; all enumerated VIO classes apply-eligible)

| Tier | Classes | Behavior |
| --- | --- | --- |
| **Apply-eligible** (still behind the per-patch approval gate, Ruling 1) | VIO-1 dangling `dmRef`, VIO-2 dangling ICN, VIO-3 hazardous step missing warning, VIO-4 illegal DMC coding, VIO-5 issue-info↔DML mismatch, VIO-7 reference cycle (warning), VIO-8 dangling DML registration | dry-run patches; apply after per-patch approval |
| **High-risk — dry-run-only** (structural rewrite or a scope judgment) | **L0 well-formedness (XML-syntax) repair**, L1 mini-XSD structural, **VIO-6 out-of-domain module** (fix = remove — a human §1.1 decision) | patch shown for review; **never** offered for apply, even under `--apply` |

> VIO-4 (illegal DMC coding) is apply-eligible per the ruling, but renaming a DMC
> ripples to every `dmRef`/DML/PM reference; the **no-new-findings guard** catches
> any ripple (the patch is rejected if it introduces dangling refs) and the
> per-patch human gate is the final backstop. L1 structural stays dry-run-only
> alongside L0 as a same-family structural rewrite — flag if you want it moved.

### Over-repair / semantic-drift guard (research §5.2)

A candidate patch is accepted (offered) only if: (a) it clears the targeted
finding; (b) it introduces **zero** new findings (validator delta strictly
non-increasing elsewhere); (c) its diff touches only the anchored node (bounded
scope). Otherwise it is rejected and the loop continues or fails closed.

## Acceptance Criteria — [AI-drafted, pending approval]

- [ ] `learnarken repair samples/package-b` (dry-run) emits a `RepairReport`:
      for each enumerated VIO finding, either a verified patch (finding cleared,
      zero new findings, minimal diff) or an explicit refusal — and writes
      nothing to `samples/package-b`
- [ ] Each apply-eligible VIO class (VIO-1/2/3/8 at minimum) has a **golden
      repair pair** (INV-3): a scripted/mocked-LLM run produces a patch that
      clears exactly that finding and introduces none
- [ ] High-risk classes (L0-syntax, VIO-6) are produced as patches in dry-run
      but **refused for apply** even under `--apply` (test-asserted)
- [ ] `--apply` with an approving stub writes atomically via the staged-commit
      path and is rollback-able; a declining stub leaves the corpus byte-identical
      (test-asserted, INV-2)
- [ ] Budget: a run that cannot make progress trips the no-progress /
      max-iterations / max-token circuit-breaker and fails **closed** (exit 3),
      never loops unbounded (test with an oscillating stub)
- [ ] Sandbox escape attempts are blocked: path traversal, network, and a
      denylisted import/command each fail inside `exec_sandbox` (test-asserted)
- [ ] Anti-collusion: the verifier tool is the deterministic validator; the fix
      is trusted only on its green re-run (documented + reflected in the report's
      `validator_delta`)
- [ ] Repair report is reproducible with a fixed seed; LLM tests are hermetic
      (scripted transcripts / mocked M3 — no live services in CI), with a
      skip-marked live suite (Day 5 precedent)
- [ ] `make test` fully green; CI green
- [ ] Red-team gate: cross-host adversarial review (+ the sandbox is a security
      focus) → `docs/reviews/day7.md` Part 1
- [ ] Branch → PR → squash → tag `v0.7.0`

## Explicitly Out of Scope (today) — [AI-drafted, pending approval]

- **No autonomous silent apply** — every write is human-gated (Ruling 1,
  constitution §1.3); no "fully autonomous production apply" is built
- **No repair of L0-syntax / L1-structural / VIO-6 via apply** — dry-run
  proposal only (Ruling 3); structural rewrite and domain-scope decisions stay
  human
- No **native function-calling** protocol (structured-JSON ReAct is the slice;
  probe native tool-calling later if M3 supports it)
- No **multi-file / cross-package refactoring** repairs; each finding is fixed at
  its anchored node
- No **semantic-entailment** judgement of fix correctness — trust basis is the
  deterministic validator re-run, not an LLM judge (research §5.4); LLM-judge
  scoring stays out
- No **learned / RL repair policy**, no fix caching, no multi-turn repair memory
- No **generalization claims** — repair success is scored only against the
  enumerated package-b VIO list (INV-3), development machine only (INV-7)
- No changes to the Day 2 validator, the Day 5 answer gates, or the Day 6 API/
  demo surface (a `repair` endpoint is Roadmap, not today)

## Risks & Open Questions

- **Daily-cycle ordering** (resolved 2026-07-17): the spec was drafted before
  step 1c 扫 (`docs/research/day7-unknowns.md`) at your direction; you authorized
  proceeding to development, then the red-team gate. The unknowns scan remains a
  same-day deliverable to backfill.
- **M3 as a ReAct driver is unproven** — it reliably emits JSON but its
  multi-step tool-selection quality is untested; the budget circuit-breaker is
  the backstop, and a low `max_iterations` default keeps cost bounded while we
  learn.
- **Risk tiers confirmed** (Ruling 1b): high-risk dry-run-only = L0-syntax + L1
  structural + VIO-6; all enumerated VIO classes apply-eligible. VIO-4's DMC-rename
  ripple is caught by the no-new-findings guard + human gate.
- **Sandbox strength is toy-scale (INV-7, definition confirmed 2026-07-17)** — an
  in-process import/command allowlist + temp-dir jail is a *real, tested*
  application-layer fence (blocks `..` traversal, network, out-of-jail writes,
  non-whitelisted calls) but **not** OS-level isolation (no nsjail/container/
  seccomp); a determined local sandbox-escape could still break out. Labeled
  toy-scale; code notes where a real kernel jail belongs. Not for adversarial
  public production.
- **Determinism of "minimal diff"** — bounding a patch to the anchored node
  needs a concrete anchor model (XPath + node identity); details land in the
  discussion memo / implementation.
