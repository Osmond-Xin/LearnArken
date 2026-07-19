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
gcloud services enable run.googleapis.com cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com
```

## 1. Create the VM (stopped-by-default demo host)

```bash
gcloud compute instances create learnarken-demo \
  --machine-type=e2-highmem-8 \
  --zone=$ZONE \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced \
  --tags=learnarken-demo
```

- `pd-balanced` (~$10/mo) over `pd-standard` (~$4/mo) on purpose: the cold
  boot reads the multi-GB embedding model from disk; standard HDD would add
  minutes to every visitor's wait (unknowns T4). This is the single standing
  cost — flag it if it should be traded the other way.
- Idle cost when stopped: disk only. Running: ~$0.36/h.

## 2. Firewall — only Streamlit and the status shim are public

```bash
gcloud compute firewall-rules create learnarken-demo-ports \
  --direction=INGRESS --action=ALLOW --rules=tcp:8501,tcp:8110 \
  --target-tags=learnarken-demo
```

The FastAPI backend (:8100), Vespa (:8080/:19071) and Neo4j (:7474/:7687)
stay loopback-bound on the VM — same security envelope as local dev.

## 3. Provision the VM

```bash
gcloud compute ssh learnarken-demo --zone=$ZONE
# on the VM:
curl -LO https://raw.githubusercontent.com/<owner>/<repo>/main/deploy/vm/provision.sh
sudo bash provision.sh https://github.com/<owner>/<repo>.git
```

## 4. Place the secrets (fails closed if skipped)

```bash
gcloud compute scp .env learnarken-demo:/tmp/.env --zone=$ZONE
gcloud compute ssh learnarken-demo --zone=$ZONE \
  --command='sudo install -o learnarken -m 600 /tmp/.env /opt/learnarken/LearnArken/.env && rm /tmp/.env'
# then re-run provision.sh if it stopped at the .env check
```

## 5. Measure the cold boot (INV-5: the page's estimate must be a measurement)

```bash
gcloud compute instances stop learnarken-demo --zone=$ZONE
time ( gcloud compute instances start learnarken-demo --zone=$ZONE && \
  until curl -fsS "http://$(gcloud compute instances describe learnarken-demo \
    --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)'):8110/demo/status" \
    | grep -q '"status": "ready"'; do sleep 5; done )
```

Record the wall time in `deploy/trigger/index.html` copy ("ready in a few
minutes" → the measured figure) and in `docs/discussions/day10.md`.

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

Deploy (TOKENS_JSON and SMTP_PASS are env config on the function, never in git;
SMTP uses a Gmail app password — create one at myaccount.google.com → Security):

```bash
gcloud functions deploy learnarken-demo-gate --gen2 \
  --region=${ZONE%-*} --runtime=python312 \
  --source=deploy/trigger --entry-point=demo_gate \
  --trigger-http --allow-unauthenticated --max-instances=2 \
  --service-account=learnarken-trigger@$PROJECT.iam.gserviceaccount.com \
  --set-env-vars=GCP_PROJECT=$PROJECT,GCP_ZONE=us-central1-a,VM_NAME=learnarken-demo,NOTIFY_EMAIL=<yi-xin-email>,SMTP_HOST=smtp.gmail.com,SMTP_PORT=465,SMTP_USER=<gmail>,SMTP_PASS=<app-password>,DEMO_GATE_KEY=<shared-key>,TOKENS_JSON='{"<token>":"<company>"}'
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
