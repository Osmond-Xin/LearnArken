# SPEC — Day 10: On-Demand Real-Stack Deployment & Wrap-Up (`v1.0.0`)

> Decision layer **transcribed from Yi Xin's verbal rulings** (2026-07-18
> session, three rounds — architecture D, cloud/GCP, trigger/status-page form;
> distilled in [docs/discussions/day10.md](../discussions/day10.md) D1–D5).
> Goal and Key Decisions are [HUMAN, transcribed]; Interfaces / Acceptance /
> Out-of-Scope / Verification are **AI-drafted, pending approval** (Day 6–9
> labeling precedent). Nothing in the decision layer is AI-invented.
>
> **Daily-cycle note.** 研 report on file
> ([day10-AI Demo 部署与展示](../gemini-deepresearch/day10-AI%20Demo%20部署与展示.md));
> 扫 ([docs/research/day10-unknowns.md](../research/day10-unknowns.md), T1–T8)
> completed **before** this SPEC. The DR's platform premise (free-tier
> HF Spaces / Streamlit CC) is **overridden** by Decision 1; its abuse-prevention,
> degradation, README and pitch chapters remain in force.
>
> **Execution-plan deviation (explicit).** execution-plan §Day 10 lists
> "Streamlit Community Cloud 或 HuggingFace Spaces". Yi Xin ruled otherwise on
> 2026-07-18: expected traffic is ~zero, paid GCP is on hand, and an on-demand
> **real stack** (zero benchmark-caveat drift) beats an always-on free-tier toy
> slice. The plan document is history and stays unedited; this SPEC records the
> deviation.

## Goal (one sentence) — [HUMAN, transcribed 2026-07-18]

Ship `v1.0.0`: a **two-layer demo** — an always-on static facade (architecture
diagram + guided explanation) plus a **token-triggered on-demand GCP VM running
the full real stack** (Vespa + Neo4j + local embedding/rerank models + MiniMax,
the same `make demo` topology, zero benchmark-caveat drift) — where the token
page shows the backend state machine (closed / starting-with-self-check /
running-with-idle-countdown), auto-shuts-down after 30 idle minutes under a $20
budget fence, notifies Yi Xin on click and on ready; plus the finalized README
and the 60-second spoken pitch (human), closing the ten-day slice.

## Key Decisions — [HUMAN, transcribed from the 2026-07-18 rulings]

1. **Architecture D — on-demand real stack; option A is dead (D1 ruling: "确定
   选型为 D，不要再 A 了").** No free-tier simplified slice, no managed-service
   substitution (B), no canned-only demo (C). Two layers: layer 0 = always-on
   static facade (README / status page content: architecture diagram, key-point
   walkthrough, EVIDENCE.md links); layer 1 = visitor-triggered full stack on a
   stopped VM. Rationale (transcribed): zero organic traffic expected; the
   trigger doubles as an **interest signal**; paid on-demand usage is affordable
   precisely because it only runs when someone cares; the deployed thing is the
   **same stack as the benchmarks** — no INV-5 caveat, no INV-7 "substituted
   backend" footnote needed.

2. **Cloud = GCP, project "My First Project" (D2 ruling: "选型确定使用 GCP…这个
   项目的钱可以直接使").** Chosen on price (same 8 vCPU/64 GB spec ~20% cheaper
   than AWS; see discussions D2 price table). Deployment goes through the
   already-authenticated local `gcloud` (verified 2026-07-18: billing enabled,
   compute API on, us-central1 quotas ample, `vmExternalIpAccess` ALLOW, budget
   permissions confirmed — existing $200 CAD monthly account alert).

3. **Trigger form: email token URL → static status/guide page (D3 ruling,
   verbatim design).** The email carries a URL with a per-recipient token.
   Clicking loads a **static page** with two purposes: (a) project guidance —
   architecture diagram and key-point explanations; (b) live backend monitoring —
   startup progress **including self-check depth**. When the backend is up and
   self-check passes, the page shows a full ready notice **plus a countdown**
   to auto-shutdown. The page always shows which state the backend is in:
   **starting (executing) / running (idle countdown) / closed**. If closed, the
   page offers **restart**, honestly explaining: "出于费用考虑，闲置 30 分钟后
   自动关闭". Design motive (transcribed): a visitor who clicks, leaves, and
   returns after 30+ minutes must never face a blank dead page — every state has
   a next action. Yi Xin is notified on click (token identifies which company)
   and again when the stack is ready.

4. **Cost fences (D4 ruling): 30-minute idle auto-shutdown + $20 budget alert.**
   Shutdown logic lives **inside the VM** (survives loss of external services —
   fail-closed to off); budget alert at $20/month on the billing account;
   trigger rate-limited per token.

5. **VM = big-memory CPU, no GPU (D5 ruling).** GPU capacity is scarce; a Spot
   GPU instance being preempted mid-interview is unacceptable. A 64 GB CPU
   machine (e2-highmem-8 baseline) runs Qwen3-8B query embedding a few seconds
   slower — accepted. Bumping to 16 vCPU is an elaboration-layer tuning knob,
   not an architecture change.

---

## Interfaces — [AI-drafted, pending approval]

### 1. `deploy/` tree (all new, no main-pipeline changes)

```text
deploy/
  vm/
    docker-compose.demo.yml   # full stack: vespa, neo4j, api, streamlit (reuses images/config from local make demo)
    provision.sh              # one-time VM setup: docker, repo clone, model prefetch (HF_HUB_OFFLINE after), .env placement
    idle_watchdog.py          # polls api /demo/status; business-idle > 30 min OR uptime > hard cap -> shutdown
    learnarken-demo.service   # systemd units: compose up on boot; watchdog timer
    learnarken-watchdog.{service,timer}
  trigger/
    main.py                   # Cloud Function gen2 (HTTP): token check + rate limit + start VM + status proxy + notify
    tokens.example.json       # format doc only — real token->recipient map NEVER committed (INV-1-adjacent)
  status-page/
    index.html                # layer-0 facade + state machine UI (inlined CSS/JS, no external resources)
  runbook.md                  # every gcloud command: enable APIs, create VM, deploy function, budget alert, DNS-free URL flow
```

### 2. App-side additions (`src/learnarken/api/app.py`)

- `GET /demo/status` — public, secret-free (unknowns T2): stage enums + booleans
  only (`vespa: ok|down`, `neo4j: ok|down`, `models: loading|ok`, `llm: ok|off`),
  plus `last_business_activity_ts` and `started_at`. Self-check reuses the
  existing `make demo` preflight logic (INV-4 fail-closed, publicly visible).
- Business-activity middleware: only answer/search/graph endpoints touch the
  activity timestamp (unknowns T1 — health/status polling never resets the
  idle clock).

### 3. Trigger function contract (`deploy/trigger/main.py`)

- `GET /?t=<token>` → serves the status page (or 403 on unknown token).
- `GET /api/state?t=<token>` → `{state: closed|starting|running, vm_ip, detail}`;
  stopped-VM state read via compute API; once VM responds, proxies `/demo/status`.
- `POST /api/start?t=<token>` → rate limit (per token, 1/hour) → `instances.start`
  → email Yi Xin ("token X / company Y clicked"). Ready-notification email to Yi
  Xin fires when state first transitions to `running`.
- Service account: `compute.instances.start/get` only — no delete, no ssh.
- Email channel: Gmail (API already enabled on the project) or SMTP app
  password — pick at implementation time, notify **Yi Xin only** (visitor gets
  the page's auto-transition, not email).

### 4. Cost-fence layering (unknowns T6)

① watchdog: business-idle 30 min → `shutdown -h now`; ② hard cap: uptime > 3 h
→ shutdown regardless of activity; ③ `$20`/month budget alert (project-scoped,
`gcloud billing budgets`); ④ existing account-level $200 CAD alert. ①② in-VM,
③④ cloud-side, mutually independent.

### 5. Demo-page cost strategy (C's legacy, discussions 未决 #1 — AI proposal)

- Preset questions dropdown → answers served from a **frozen cache** (zero API
  cost, DR §2 pre-generated caching).
- Free-text input → live MiniMax, guarded by: input length cap, per-session call
  cap, and MiniMax failure → **explicit refusal** (INV-4 wording, not a stack
  trace).

### 6. README finalization + pitch support

- README final pass per execution-plan: demo section (how the on-demand demo
  works + honest cost-fence note), Quickstart ≤3 commands, benchmark table
  pointing at EVIDENCE.md, architecture diagram from `docs/diagrams/rendered/`,
  AI-first section linking AI-COLLABORATION.md, honest Roadmap layers.
- Demo GIF: recorded by Yi Xin (or AI-scripted capture if tooling allows) —
  compressed ≤5 MB (DR §4).
- 60-second pitch: **human deliverable** (tutorials/12), AI may lint the draft
  against EVIDENCE.md claims only.

## Acceptance Criteria — [AI-drafted, pending approval]

1. **Cold path**: clicking a valid token URL on a stopped VM shows the page in
   `closed→starting` with real per-stage self-check progress, and reaches
   `running` with a working end-to-end demo (real stack answers a question with
   citations) — startup estimate on the page comes from a measured boot, not a
   guess (unknowns T4).
2. **Idle path**: 30 min without business calls (status polling running the
   whole time) → VM shuts itself down; page shows `closed` + restart affordance
   + honest cost explanation. Status polling provably does NOT reset the clock
   (unit test).
3. **Fence stack**: $20 project budget alert exists (`gcloud billing budgets
   list` shows it); hard-cap shutdown unit-tested; rate limit returns a polite
   refusal on the 2nd start within an hour.
4. **Notifications**: Yi Xin receives click-notify and ready-notify emails in a
   live drill.
5. **Secrets/INV-1**: no token map, no `MINIMAX_*`, no service-account key in
   git (guarded by inspection + existing evidence tests still green).
6. `make test` + `make lint` green (295+9 baseline unbroken); new unit tests for
   token validation, rate limiting, idle/hard-cap decision logic (pure functions,
   no cloud calls).
7. README finalized; `docs/EVIDENCE.md`/`llms.txt` untouched numbers still pass
   the Day 9 drift guard.
8. Cross-host `coding-adversarial-review` run on the day's diff → findings in
   `docs/reviews/day10.md` Part 1 (automatic gate, before any merge proposal).
9. Tag `v1.0.0` after Yi Xin's adjudication + journal (human).

## Out-of-Scope — [AI-drafted, pending approval]

- **No free-tier deployment** (HF Spaces / Streamlit CC slice) — Decision 1
  killed it; not even as fallback.
- **No keep-alive heartbeat hacks** (GitHub Actions pinging) — the sleep/wake
  states are displayed honestly instead.
- **No custom domain / HTTPS termination** — plain `http://<ephemeral-ip>` with
  an on-page note (unknowns T8 option a); nip.io/Caddy only if the day has
  slack, else Roadmap.
- **No Secret Manager migration** — `.env` on the VM disk (unknowns T5 option a),
  Secret Manager to Roadmap.
- **No multi-user concurrency hardening, no CDN, no autoscaling** — one visitor
  at a time is the honest scale.
- **AI does not write `docs/journal/day10.md`, the adjudication Part 2, or the
  spoken pitch** (INV-6).
- **No changes to retrieval/graph/eval pipelines** — deployment wraps the stack,
  never edits it.

## Verification (how to check) — [AI-drafted, pending approval]

```bash
make test && make lint                      # baseline + day10 unit tests green
uv run pytest tests/test_day10_deploy.py -q # token/ratelimit/idle pure-logic tests
# live drill (documented in deploy/runbook.md):
#   1. gcloud compute instances stop learnarken-demo
#   2. open https://<function-url>/?t=<test-token>  -> closed -> start -> starting(stages) -> running
#   3. ask one preset + one free-text question end-to-end
#   4. wait 30 min idle (page polling active) -> VM off, page shows closed+restart
#   5. check both notification emails arrived; gcloud billing budgets list shows $20 alert
```

Then the automatic cross-host red-team gate on the diff → `docs/reviews/day10.md`
Part 1 → Yi Xin adjudicates (Part 2), re-runs numbers, writes the journal, tags
`v1.0.0`.
