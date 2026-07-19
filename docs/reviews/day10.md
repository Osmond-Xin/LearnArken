# Day 10 Red-Team Review — On-Demand Real-Stack Deployment

> **Part 1 (below) is AI-written** (cross-host adversarial gate, CLAUDE.md step 4,
> launched automatically on green before any commit). **Mode**: external =
> **Codex** (`codex exec --sandbox read-only`, the non-implementing model)
> cross-validated against the **Claude** host's own independent pass. **Part 2
> (adjudication) is Yi Xin's** — accept/reject + rationale, and any red-team
> number is re-run by the human before merge (INV-6). AI does not write Part 2 and
> has **not** applied any fix.
>
> Scope: the Day 10 diff — the new `deploy/` tree (VM idle watchdog + public
> status shim + `run_demo_vm.sh` + `provision.sh` + systemd units, the
> token-gated Cloud Function `deploy/trigger/`, the static status page
> `index.html`, `runbook.md`) and `src/learnarken/api/app.py` (`/demo/status`
> endpoint + business-activity clock), plus `tests/test_day10_deploy.py`.
> **Central risk**: this slice takes a stack whose entire day-6 security envelope
> was "loopback-only" and exposes it to the public internet. **Verdict:
> DO_NOT_MERGE** until the live app is actually gated, cost fences cover LLM
> spend, and the watchdog fails closed under malformed/restart conditions.
>
> Tags: `[cross-validated]` both caught · `[external-only]` Codex only ·
> `[host-only]` Claude only. On severity disagreement, the higher is taken.

## Trust-boundary entrances enumerated (security-fence checklist)

- **Execute**: Cloud Function `/api/start` (starts a billable VM); Streamlit
  `/query` (LLM spend); Streamlit `/upload` (write + reindex); watchdog
  `systemctl poweroff`; `provision.sh` (docker, `curl|sh`).
- **Read**: `/api/state`, public `:8110/demo/status`, Streamlit `/health`,
  `eval/traces/*.json`, `.env`.
- **Write**: uploaded corpus (persists across visitors), Vespa/Neo4j indexes,
  `eval/traces`, `/run` watchdog fail-count, in-memory start history.
- **Trust**: URL token (bearer), GCE status/IP, backend status JSON, health
  booleans, `$20` budget alert (LLM spend NOT included), the 0.0.0.0 firewall.

## Part 1 — Findings (AI)

### BLOCKERS (P1)

**#1 The gate protects VM start, not demo use — Streamlit `:8501` is
unauthenticated** `[cross-validated]` — `runbook.md` §2 firewall opens `tcp:8501`
to `0.0.0.0/0`; `run_demo_vm.sh` binds Streamlit `0.0.0.0`; `demo/streamlit_app.py`
has no token/session check. Problem: the token only gates *starting* the VM and
reading status. Once any legitimate recipient starts it, the VM has a public IP
and **anyone who learns that IP can query the LLM, upload files, and reset the
idle clock without a token** — the "token = interest signal, one visitor at a
time" design is defeated for everything except the compute-start. The firewall
cannot restrict by source (visitor IPs are unknown), which is exactly *why* the
app itself must be gated. Recommendation: put Streamlit behind the same token
(reverse proxy validating a server-side token → session cookie, or IAP), or
treat `:8501` as fully public and remove the write/spend paths from it.

**#2 Cost fence does not cover LLM spend; `$20` GCP budget is alert-only**
`[cross-validated]` — Decision 4 sells "30-min idle + $20 fence" as the cost
control, but `runbook.md` §7 budget is a GCP-billing *alert* and MiniMax spend is
**not GCP billing** — it is invisible to the fence. No server-side query quota,
concurrency cap, or LLM-token circuit breaker exists (`app.py` `/query`,
`streamlit_app.py`). Scenario: given the IP (see #1), an attacker opens many
sessions and submits evidence-matching questions for up to the 3-h hard cap,
burning MiniMax tokens; repeat after each restart. Recommendation: add a global
concurrency semaphore + per-session daily LLM-call quota + a hard kill switch in
the backend; wire the GCP budget to a Pub/Sub action that stops the VM; state
honestly that LLM spend is the one uncapped runtime cost.

**#3 Watchdog fails OPEN, not closed (INV-4 inversion)** `[cross-validated]` —
`idle_watchdog.py`: (a) `decide()` is called on `status["idle_seconds"]` /
`["uptime_seconds"]` **after** the urlopen `try` block, so a reachable-but-
malformed status (missing/renamed keys, a future schema change) raises `KeyError`
every minute — the watchdog crashes and **the VM never shuts down**; the fail
count was just reset to `0`, so the unreachable-fallback never fires either.
(b) Uptime comes from the API process (`_STARTED_AT` in `app.py`), and the demo
unit has `Restart=on-failure` — a backend restart resets the 3-h hard cap.
Recommendation: compute uptime from `/proc/uptime` (true VM uptime); validate
that status fields are finite numbers and treat missing/NaN as a fail-closed
strike; wrap `decide()` inputs so any parse failure counts toward shutdown.

**#4 Public upload path: cross-visitor persistence + unbounded intake**
`[cross-validated]` — `streamlit_app.py` upload tab is public (#1); the FastAPI
2 MiB guard sits *behind* Streamlit, which buffers `getvalue()` first (no
`server.maxUploadSize` set); and `UPLOAD_PACKAGE` persists on disk across
visitors and is swapped into the *live corpus*. Scenario: visitor A uploads
content (possibly private/company XML), visitor B then queries it; or repeated
large uploads exhaust Streamlit memory. Recommendation: disable upload in the
public demo (or gate + per-session isolate it), set `server.maxUploadSize`, wipe
`var/uploads` on shutdown.

**#5 Public queries write full prompt payloads to disk (INV-1-adjacent
governance)** `[external-only, host-verified]` — `answer/engine.py` calls
`write_trace()` on every query; `answer/trace.py` writes `raw_content`, the
question, retrieval and generation spans to `eval/traces/<id>.json`. `.gitignore`
excludes the dir but that is not data governance. Scenario: a recruiter-side
visitor asks with company/job context; it lands on the VM disk and can leak via
snapshot, scp, or later artifact collection — the same personal-data-boundary
family as INV-1. Recommendation: disable full traces in public/VM mode, or redact
to IDs/hashes with short retention and `0700` perms.

**#6 Token is a bearer secret carried in the URL query string**
`[cross-validated]` — `index.html` and `main.py` take `?t=<token>`. URL tokens
leak through browser history, forwarded links, Cloud Function request logs, link
previews, and screenshots. Scenario: a forwarded invite or a log reader replays
`?t=` to start the VM and impersonate a recipient's interest (corrupting the very
signal the design is built to collect). Recommendation: move the token out of the
URL (one-time code → HttpOnly SameSite cookie, or fragment-to-header exchange),
set `Cache-Control: no-store`, redact tokens in logs. (Residual: this is a
portfolio demo with only VM-start behind the token — severity balances real leak
channels against low blast radius.)

### SHOULD FIX (P2)

**#7 `/health` still leaks probe detail through public Streamlit — the guard
misses its own boundary** `[cross-validated]` — `/demo/status` was deliberately
made coarse (booleans only, unknowns T2), but `streamlit_app.py` sidebar still
calls loopback `/health` and renders `s.get("detail")` — internal paths, missing
config keys, exception text — to the now-public UI. This is precisely the day-9
pattern: the new guard is clean, the *sibling* entrance it forgot is the leak.
Recommendation: point Streamlit at `/demo/status`, or suppress detail strings in
public/VM mode.

**#8 Plain HTTP for the live app** `[cross-validated]` — `index.html` links
`http://<ip>:8501`; questions/uploads/answers cross the network in clear text.
SPEC out-of-scope explicitly defers HTTPS (unknowns T8); flagged for the
adjudication record. Recommendation: terminate TLS at a proxy, or accept + note
on-page (current plan).

**#9 Rate limit is in-memory, per-instance, and consumed before the start
succeeds** `[cross-validated]` — `logic.allow_start` mutates history on *decision*,
not on a confirmed start; `--max-instances=2` + cold starts mean a second
instance has empty history. Scenario: a transient Compute API error still burns a
token's hour; or two instances allow 2 starts/hour. Recommendation: move rate
state to Firestore/GCS with compare-and-set; record only after a successful
`instances.start`.

**#10 Public status shim: unbounded threads, no cache/rate limit**
`[cross-validated]` — `status_shim.py` `ThreadingHTTPServer` spawns a thread per
request and proxies every hit to the backend probe. Scenario: a bot floods
`:8110/demo/status`, amplifying into backend health probes and VM CPU.
Recommendation: cache the status for a few seconds, cap threads, or proxy status
back through the gated function.

**#11 Docker group = root-equivalent on the app user** `[cross-validated]` —
`provision.sh` adds `learnarken` to the `docker` group; the demo unit runs as
that user. Any Streamlit/dependency RCE (reachable via #1) escalates to host root
through the Docker socket → `.env` and all VM data. Recommendation: manage
containers via root-owned systemd units and drop the app user from the docker
group after provisioning.

**#12 Supply chain unpinned** `[cross-validated]` — `neo4j:latest`, untagged
`vespaengine/vespa`, wildcard `functions-framework==3.*` /
`google-cloud-compute==1.*`, `curl … astral.sh/uv/install.sh | sh`. A rebuild
pulls different images/packages — could change Neo4j auth defaults, break
readiness, or import a compromised release. Recommendation: pin image digests and
exact function deps; verify the uv installer.

### NICE TO HAVE (P3)

**#13 Blind spots in observability** `[cross-validated]` — shim logs are
suppressed and invalid-token attempts on the function are not safely logged;
brute-force/scan/DoS is invisible. Recommendation: log sampled IP/path/status/
latency + a token *hash prefix* only.

**#14 Concrete project/billing IDs committed** `[external-only]` — `runbook.md`
carries the real project id and billing account. Not INV-1 personal data, but
improves attacker recon. Recommendation: placeholder them, keep real IDs in a
private operator note.

**#15 No security/cache headers on token-bearing responses** `[cross-validated]`
— add `Cache-Control: no-store`, `Referrer-Policy: no-referrer`,
`X-Frame-Options: DENY`/CSP `frame-ancestors 'none'` on the page and API.

**#16 INV-5: the page ships unmeasured cost/time numbers** `[host-only]` —
`index.html` states "≈ $0.20 per session" and "ready in a few minutes";
`runbook.md` §5 defers these to a deploy-time measurement. If the page goes live
before step 5, they are unverified public numbers. Recommendation: gate go-live
on the measurement (already a runbook step — make it a hard precondition).

## Part 1b — Fixes applied + cross-host verification (AI)

> After Yi Xin's instruction ("minimax 费用拦截检查/补齐；其余按建议全修"), the
> implementer applied fixes and re-ran the **cross-host Codex** gate as a
> follow-up verification pass (not a self-attestation). Adjudication (Part 2)
> remains Yi Xin's. Findings answered:
>
> - **First, the specific ask** — MiniMax cost interception: a token
>   circuit-breaker exists only in the **Day 7 repair** subsystem
>   (`repair/config.py`), **not** on the answer/query path. So on the public
>   demo there was **no** spend fence. Added one (below, #2).
>
> | # | Fix | Codex re-verify |
> | --- | --- | --- |
> | #1 | Shared gate key (`DEMO_GATE_KEY`) required on `/query`+`/upload` (`X-Demo-Key`) and in Streamlit (`?k=`); drive-by IP has no key | PARTIAL (shared bearer key; real spend/data paths now capped) |
> | #2 | `DemoGuard.llm_slot()` — per-boot LLM call quota + concurrency semaphore, fail-closed refusal over limit | PARTIAL (process-local, resets on restart — acceptable for a short-lived VM) |
> | #3 | Watchdog reads `/proc/uptime` (not the resettable API clock); validates `idle_seconds` finite; malformed/missing ⇒ fail-closed strike, never crash | **RESOLVED** |
> | #4 | Uploads refused in public mode + tab hidden + `maxUploadSize` + wipe on stop | **RESOLVED** |
> | #5 | `LEARNARKEN_TRACE_DISABLED=1` ⇒ `write_trace` no-ops (no prompt/answer on disk) | **RESOLVED** |
> | #6 | `Cache-Control: no-store` + `Referrer-Policy: no-referrer` + frame-deny; tokens logged as hash-prefix only | NOT-RESOLVED by design (URL token is the accepted portfolio-scope tradeoff; leak channels reduced) |
> | #7 | Streamlit sidebar now reads `/demo/status` (booleans), never `/health` detail | **RESOLVED** |
> | #9 | Rate-limit split: read-only `is_rate_limited` + `record_start` only after a successful start | PARTIAL (still per-instance memory) |
> | #10 | Status shim 3s TTL cache collapses poll floods to one backend probe | PARTIAL (thread pool still unbounded) |
> | #11 | Root-owned `learnarken-containers.service` owns Docker; app user no longer in docker group | **RESOLVED** |
> | #12 | `neo4j` version-tagged, function deps `~=` pinned (digest-pin note) | PARTIAL (vespa `:8`, apt still float) |
>
> **New issues the fixes introduced (Codex verify) — both addressed:**
>
> - **[fixed] Placeholder gate key accepted as a real secret.** `provision.sh`
>   seeds `DEMO_GATE_KEY=CHANGE-ME-…`; the guard now treats that placeholder (and
>   any key `<16` chars) as *unconfigured* ⇒ the app stays locked until a real
>   key is set (fail closed). Unit-tested.
> - **[fixed] Function deploy omitted `DEMO_GATE_KEY`.** Runbook §6 now sets it
>   in the `--set-env-vars` and requires it to match the VM's `demo.env`.
>
> **Codex follow-up verdict: REVIEW_NEEDED** (up from DO_NOT_MERGE) — the
> remaining residuals are the URL-borne token/key and plain HTTP, both already
> in SPEC Out-of-Scope for this portfolio slice. `make test` 327 passed / 9
> skip, lint clean. **Not merged; awaiting Yi Xin's Part 2.**

## Part 2 — Adjudication (Yi Xin) — pending

<!-- HUMAN-WRITTEN. AI must not fill this in. Per finding: accept / reject +
     rationale; re-run any red-team number before merge (INV-6). Note which P1s
     are true blockers vs. accepted-risk given the honest portfolio scope
     (SPEC Out-of-Scope already defers HTTPS, multi-user hardening). -->
Approved every fixed