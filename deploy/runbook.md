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
achieves RCE (red team R-09). Nothing on this VM calls a Google API.

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
  --permissions=compute.instances.start,compute.instances.get,compute.zoneOperations.get

gcloud compute instances add-iam-policy-binding learnarken-demo \
  --zone=$ZONE \
  --member=serviceAccount:learnarken-trigger@$PROJECT.iam.gserviceaccount.com \
  --role=projects/$PROJECT/roles/learnarkenDemoStarter
```

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

Each line carries `recipient=<company>` (from your private token→company note)
and a token hash tag — never the raw token.

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
```
