# Deploy Runbook — On-Demand Demo on GCP (SPEC day10)

> This file is the terse command reference. For a step-by-step walkthrough with
> a pre-deploy checklist, explanations, day-to-day usage and troubleshooting,
> see [DEPLOY-GUIDE.zh.md](DEPLOY-GUIDE.zh.md) (operator guide, Chinese).
>
> **AI-drafted** (Day 10 elaboration layer, pending review). Zone
> `us-central1-a` (verified 2026-07-18: billing on, compute API on, quotas
> ample, `vmExternalIpAccess` ALLOW). Every mutating command below is meant to
> be run **once**, from the repo root, by a human or with a human watching.
> Secrets (`.env`, tokens, SMTP app password) never enter git (INV-1).
>
> **Fill these from your private operator note (day10 #14 — concrete project /
> billing IDs are kept out of the repo):**
>
> ```bash
> export PROJECT=<gcp-project-id>          # e.g. the "My First Project" id
> export PROJECT_NUMBER=<gcp-project-number>
> export BILLING=<billing-account-id>      # e.g. 0XXXXX-XXXXXX-XXXXXX
> export ZONE=us-central1-a
> ```

## 0. One-time API enablement

```bash
gcloud services enable compute.googleapis.com run.googleapis.com \
  cloudfunctions.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com billingbudgets.googleapis.com
```

Compute / Artifact Registry / Billing Budgets are often already on in an
established project; a genuinely fresh one needs all six (red team R-20).

## 1. Create the VM (stopped-by-default demo host)

```bash
gcloud compute instances create learnarken-demo \
  --machine-type=c3-highmem-8 \
  --zone=$ZONE \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced \
  --tags=learnarken-demo \
  --no-service-account --no-scopes
```

`--no-service-account`: an internet-facing VM running third-party Python must
not carry project credentials its metadata server will hand to anything that
achieves RCE (red team R-09).

> **Amended 2026-07-30** — this is no longer how the deployed VM is
> configured. It now carries a service account holding exactly
> `roles/logging.logWriter`, so that what a visitor does on the demo survives
> the boot. §9 records the trade and the reasoning; the shape above is still
> the right *starting* point, and §9 is the smallest possible step away from
> it.

- `pd-balanced` (~$10/mo) over `pd-standard` (~$4/mo) on purpose: the cold
  boot reads the multi-GB embedding model from disk; standard HDD would add
  minutes to every visitor's wait (unknowns T4). This is the single standing
  cost — flag it if it should be traded the other way.
- **Deployed machine type is `c3-highmem-8`, not `e2-highmem-8`**: on
  2026-07-29 `e2-highmem-8` (and `n2`/`n2d`) had no capacity in `us-central1-a`,
  so the demo runs on `c3-highmem-8` (same 8 vCPU / 64 GB). ~$0.53/h vs ~$0.36/h
  — about $0.16 per demo session instead of $0.11; the standing disk cost is
  unchanged. **The measured 196 s cold boot and every constant derived from it
  were measured on `c3`** — re-measure if you rebuild on a different class
  (round-2 red team).
- Idle cost when stopped: disk only — **100 GB pd-balanced is ~$10/month**, not
  the ~$4 a `pd-standard` disk would cost (red team R-10: the guide quoted the
  cheaper disk's price under the more expensive disk's config). Running: ~$0.36/h.

## 2. Firewall — only Streamlit and the status shim are public

```bash
gcloud compute firewall-rules create learnarken-demo-ports \
  --direction=INGRESS --action=ALLOW --rules=tcp:8501,tcp:8110 \
  --target-tags=learnarken-demo
```

The FastAPI backend (:8100), Vespa (:8080/:19071) and Neo4j (:7474/:7687)
stay loopback-bound on the VM — same security envelope as local dev.

"Only 8501 and 8110 are public" is **false until you also shadow the VPC's
default SSH rule** (`default-allow-ssh`, 0.0.0.0/0, priority 65534 — red team
R-08). Lower priority number wins:

```bash
gcloud compute firewall-rules create learnarken-demo-ssh-allow \
  --direction=INGRESS --action=ALLOW --rules=tcp:22 --priority=900 \
  --source-ranges=<your-ip>/32,35.235.240.0/20 --target-tags=learnarken-demo
gcloud compute firewall-rules create learnarken-demo-ssh-deny \
  --direction=INGRESS --action=DENY --rules=tcp:22 --priority=950 \
  --source-ranges=0.0.0.0/0 --target-tags=learnarken-demo
```

`35.235.240.0/20` is IAP's range, so `--tunnel-through-iap` keeps working when
your home IP changes.

## 3. Provision the VM

```bash
gcloud compute ssh learnarken-demo --zone=$ZONE
# on the VM — pin the commit, do not track a moving branch (red team R-11):
curl -LO https://raw.githubusercontent.com/<owner>/<repo>/<commit-sha>/deploy/vm/provision.sh
sudo bash provision.sh https://github.com/<owner>/<repo>.git
```

If you are iterating on the script itself, `gcloud compute scp` your local copy
instead — what runs must be what you edited, not what `main` happened to hold.

## 4. Place the secrets (fails closed if skipped)

```bash
gcloud compute scp .env learnarken-demo:~/.env.staged --zone=$ZONE
gcloud compute ssh learnarken-demo --zone=$ZONE \
  --command='sudo install -o learnarken -m 600 ~/.env.staged /opt/learnarken/LearnArken/.env && shred -u ~/.env.staged'
# then re-run provision.sh if it stopped at the .env check
```

Staged in your own home directory rather than `/tmp` (world-readable, and every
other process on the box can watch it appear — red team R-13).

> **Keep `.env`'s `NEO4J_PASSWORD` equal to `learnarken`** — `provision.sh`
> creates the container with `NEO4J_AUTH=neo4j/learnarken` and its readiness
> check is unauthenticated, so a different password would look healthy and then
> fail every query with 401 (red team R-17).

## 5. Measure the cold boot (INV-5: the page's estimate must be a measurement)

```bash
gcloud compute instances stop learnarken-demo --zone=$ZONE
time ( gcloud compute instances start learnarken-demo --zone=$ZONE && \
  until curl -fsS "http://$(gcloud compute instances describe learnarken-demo \
    --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)'):8110/demo/status" \
    | grep -q '"status": "ready"'; do sleep 5; done )
```

**Measured 2026-07-29: 196 s** (`c3-highmem-8`, 100 GB pd-balanced, model
already in the HF cache) from `instances start` to `"status": "ready"`. The page
copy and `idle_watchdog.BOOT_GRACE_S` are derived from this figure (INV-5) —
re-measure and update both if the machine type or the model changes.

Note what "ready" now means: it waits for `models_warm`, so the ~100 s the
embedding model spends loading is *inside* the 196 s rather than dumped on the
first visitor (red team R-14).

## 6. Trigger function — least-privilege service account, then deploy

```bash
gcloud iam service-accounts create learnarken-trigger

gcloud iam roles create learnarkenDemoStarter \
  --project=$PROJECT \
  --permissions=compute.instances.start,compute.instances.get,\
compute.instances.setLabels,compute.zoneOperations.get

gcloud compute instances add-iam-policy-binding learnarken-demo \
  --zone=$ZONE \
  --member=serviceAccount:learnarken-trigger@$PROJECT.iam.gserviceaccount.com \
  --role=projects/$PROJECT/roles/learnarkenDemoStarter
```

`compute.instances.setLabels` is what the start lock writes with (one label,
`demo-start-lock`, on the VM itself — the fingerprint precondition is the
compare-and-swap). It was **missing** from the role as first deployed, which
the function survives by design — a lock it cannot write is logged and the
start proceeds unlocked — but without it the lock is decorative. If you rebuild
the role, keep this permission in it.

Generate tokens (one per recipient — the token IS the interest signal):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

Deploy. `TOKENS_JSON` is env config on the function, never in git. Prefer
`--env-vars-file=<yaml outside the repo>` over the `--set-env-vars` line below:
a flag lands in shell history, and a comma inside `TOKENS_JSON` silently splits
the whole variable list (red team R-13).

**Email is optional and off by default** (Yi Xin, 2026-07-29): applications go
out through LinkedIn and web forms, so there is no mailbox to send from. Leave
`SMTP_*` and `NOTIFY_EMAIL` unset — `_notify` then no-ops cleanly. The interest
signal still works, because it was never the email: it is the per-recipient
token. Read who opened a link from the function log:

```bash
gcloud functions logs read learnarken-demo-gate --region=${ZONE%-*} --gen2 \
  --limit=50 | grep -E 'demo link opened|VM start issued'
```

Each line carries `recipient=<label>` (from your private token→company note) and
a token hash tag. **The function never writes the raw token — but Cloud Run's
own request log does**, in `httpRequest.requestUrl`, before any of this code
runs. The tokens are therefore in Cloud Logging in the clear for anyone with log
access on the project. That is you; it is not a visitor-facing leak, but do not
describe the setup as keeping tokens out of logs.

### Reading the signal honestly: a fetch is not a person

One token per **channel**, not per company, is the useful granularity when the
same company is approached twice (the first application, 2026-07-30, went to
Arken through a web form and through LinkedIn: labels `arken-web-form` and
`arken-linkedin`).

A link posted into LinkedIn or a web form can be fetched by a **preview crawler
or a security scanner** the moment it is sent — which logs an "opened" event no
human caused. The user agent tells them apart, and it is only in the request
log, not in the function's line:

```bash
gcloud logging read \
  'resource.labels.service_name="learnarken-demo-gate" AND httpRequest.requestMethod="GET"' \
  --freshness=7d --format='value(timestamp,httpRequest.userAgent,httpRequest.status)'
```

A real reader looks like a browser (`Mozilla/5.0 …`) and is followed within
seconds by repeated `/api/state` polls from the page's own JavaScript. A crawler
fetches `/` once, names itself (`LinkedInBot`, `Slackbot`, `facebookexternalhit`,
`curl`), and never polls. **`VM start issued` is the only signal no crawler
produces**: it takes a click on the page.

```bash
gcloud functions deploy learnarken-demo-gate --gen2 \
  --region=${ZONE%-*} --runtime=python312 \
  --source=deploy/trigger --entry-point=demo_gate \
  --trigger-http --allow-unauthenticated --max-instances=2 \
  --service-account=learnarken-trigger@$PROJECT.iam.gserviceaccount.com \
  --set-env-vars=GCP_PROJECT=$PROJECT,GCP_ZONE=$ZONE,VM_NAME=learnarken-demo,DEMO_GATE_KEY=<shared-key>,TOKENS_JSON='{"<token>":"<company>"}'
```

`DEMO_GATE_KEY` **must be the same value** set in the VM's
`/opt/learnarken/demo.env` (provision step) — the function embeds it in the
demo link so the visitor's Streamlit and the backend accept the session. Use a
strong random value (`python3 -c "import secrets; print(secrets.token_urlsafe(24))"`);
the committed placeholder is rejected by the app (fail closed).

The visitor URL is `https://<function-url>/?t=<token>`.

## 7. Budget fence ($20 alert, Decision 4 — layered on the existing $200 CAD account alert)

```bash
gcloud billing budgets create \
  --billing-account=$BILLING \
  --display-name="LearnArken demo fence" \
  --budget-amount=20 \
  --filter-projects=projects/$PROJECT_NUMBER \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0
```

(Amount is in the billing account's currency — CAD here.)

## 8. Acceptance drill (maps to SPEC acceptance 1–4)

1. Stop the VM. Open the token URL → page shows **closed** + honest cost note.
2. Click start → **starting** with real self-check stages → **running** with
   countdown; open the demo link, ask one preset and one free question.
3. Verify both emails arrived (click-notify, ready-notify).
4. Leave it idle 30 min with the page open (polling running) → VM powers off,
   page returns to **closed** with a restart button.
5. `gcloud billing budgets list --billing-account=$BILLING` shows
   the $20 fence.

## 9. Visitor logging — what happened *on* the demo (added 2026-07-30)

**Why.** On 2026-07-30 a real visitor (Bell Canada address in Nova Scotia, not
the maintainer's own network) opened the `arken-web-form` link, clicked start,
and the VM ran its full 34 minutes before self-stopping. The complete record of
that visit was two lines from the gate function — `demo link opened` and
`VM start issued`. Whether they asked anything, what they asked, whether the
answer was refused: unrecorded, because the demo's own logs went to journald on
a machine that was then powered off. The successful `/query` path did not log
at all; only failures did.

**The trade.** This reverses part of §1. The VM now has an identity, so an RCE
on it yields a token — and that token can do exactly one thing: write log
entries into this project. It cannot read data, start or stop instances, touch
billing, or reach any other API. The realistic abuse is log spam, whose cost is
Cloud Logging ingestion (first 50 GiB/month free; a 30-minute session produces
single-digit MB), and whose ceiling is already watched by the $20 budget alert.
That was judged worth paying for a record of who actually tried the demo.

```bash
# 9a. A service account that can do one thing.
gcloud iam service-accounts create learnarken-demo-vm \
  --display-name="LearnArken demo VM (logging only)"

VM_SA=learnarken-demo-vm@$PROJECT.iam.gserviceaccount.com
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$VM_SA" --role=roles/logging.logWriter

# 9b. Attach it. The VM must be TERMINATED for this; the scope is the
#     narrowest one that exists — logging.write, not cloud-platform.
gcloud compute instances set-service-account learnarken-demo --zone=$ZONE \
  --service-account=$VM_SA \
  --scopes=https://www.googleapis.com/auth/logging.write

# 9c. One boot: move the VM to the reviewed commit, install the agent, restart
#     the app. SHA must already be on origin — the VM fetches from there.
gcloud compute instances start learnarken-demo --zone=$ZONE
SHA=<the merged commit>
gcloud compute ssh learnarken-demo --zone=$ZONE --command "
  sudo -u learnarken git -C /opt/learnarken/LearnArken fetch origin $SHA &&
  sudo -u learnarken git -C /opt/learnarken/LearnArken checkout --detach $SHA &&
  sudo bash /opt/learnarken/LearnArken/deploy/vm/install_ops_agent.sh &&
  sudo systemctl restart learnarken-demo"
```

Three things that are easy to get wrong here, all found by checking the live
VM's actual state rather than assuming it:

- **The checkout is detached and owned by `learnarken`** (provision pins a SHA,
  R-11). `sudo git pull` fails twice over — no upstream branch on a detached
  HEAD, and root touching another user's repo trips git's dubious-ownership
  guard. Fetch the SHA as `learnarken`, exactly as `provision.sh` does.
- **The agent alone changes nothing.** The lines it ships are written by the new
  backend code, so the VM has to move to the new commit *and* restart
  `learnarken-demo`. Agent first, restart second, so the app's output is
  captured from its first line.
- **The commit must be on `origin` first.** Until the branch is merged and
  pushed, there is nothing for the VM to fetch.

Leave the VM to its own 30-minute idle watchdog afterwards, or stop it by hand.

**Reading it back**, any time, without booting anything:

```bash
# What visitors asked, and how each one ended.
gcloud logging read \
  'resource.type="gce_instance" AND jsonPayload.event="demo_query"' \
  --limit=50 --format="value(timestamp,jsonPayload.turn,jsonPayload.outcome,jsonPayload.question)"

# How the question was entered: a suggestion button, or typed.
gcloud logging read \
  'resource.type="gce_instance" AND jsonPayload.event="demo_entry"' \
  --limit=50 --format="value(timestamp,jsonPayload.turn,jsonPayload.source)"
```

Each line is *exactly* one JSON object, so a question containing a newline
cannot forge an extra entry, and selection is on `jsonPayload.event` rather
than a substring the visitor could simply type into their question. `turn`
pairs the two lines of the same turn. Both are emitted **only** under
`DEMO_PUBLIC=1`: local `make demo` and the test suite log nothing.

Three things to know before trusting what you read:

- **These are telemetry, not audit records.** They are written by the VM with
  the VM's own credential, so anything that owns the VM can write them too.
  Cloud Audit Logs (who started the instance, from the gate function) are the
  trustworthy half; treat a `demo_query` line as "the demo says this happened".
- **The whole journal ships, not just these two lines** — sshd, systemd, the
  containers. That is deliberate (a demo that broke should be diagnosable
  afterwards), and it is why the retention below matters. Measured 2026-07-30:
  the shipped Streamlit logs no request lines at all, so the `?k=` gate key
  does not reach the journal by that route.
- **Volume is the cost.** Ingestion is free to 50 GiB/month and a 30-minute
  session is single-digit MB, but a compromised VM could write until the $20
  budget alert fires. That alert is the fence; there is no other.

Entries land in the `_Default` bucket and expire on its retention (30 days
unless changed) — if a visit matters for the job search, copy it out rather
than trusting the bucket to keep it.

## Fence layering (unknowns T6, for the record)

① in-VM watchdog: 30 min business-idle → poweroff; ② in-VM hard cap: 3 h
uptime → poweroff regardless of activity; ③ $20/month project budget alert;
④ pre-existing $200 CAD account-level alert. ①② keep working if every external
service disappears; ③④ keep working if the VM misbehaves.

## Teardown (after the job search ends)

```bash
gcloud functions delete learnarken-demo-gate --region=${ZONE%-*}
gcloud compute instances delete learnarken-demo --zone=$ZONE
gcloud compute firewall-rules delete learnarken-demo-ports
gcloud iam service-accounts delete \
  learnarken-demo-vm@$PROJECT.iam.gserviceaccount.com
```
