# LearnArken 在线 Demo 部署指南（按需真栈）

> 面向操作者（Yi Xin）的完整手册。用途：**求职投递前，把在线 Demo 提前部署好**，
> 之后给招聘方发一个点击即启动的链接。跑的是与基准同源的完整栈（Vespa + Neo4j +
> 本地嵌入/重排模型 + MiniMax），停机时几乎零成本，闲置自动关机。
>
> 命令的**权威来源**是 [runbook.md](runbook.md)；本文是带解释、准备清单和排错的
> 叙述版，两者命令一致。敏感 ID/密钥不写进仓库（红队 #14）——从你的私人笔记填入。

---

## 0. 这套东西是怎么跑起来的（先建立心智模型）

```
招聘方点邮件里的 token 链接
        │
        ▼
Cloud Function（常驻，免费）── 校验 token ──► 静态状态页
        │                                    │轮询
        │点 "启动"                            ▼
        ├──► 开机 GCP VM（停机→运行）    显示 closed/starting/running + 倒计时
        │                                    │就绪后给出带 key 的 demo 链接
        ▼                                    ▼
   给你发邮件（谁点了/已就绪）        招聘方用 Streamlit 提问（真栈作答）
        │
    VM 内看门狗：闲置 30 分钟 or 开机满 3 小时 → 自动关机
```

- **停机时只付磁盘**（约 $4/月）；**运行时** e2-highmem-8 约 $0.36/小时，一次演示
  约 $0.18–0.30。
- 三处独立的成本围栏：VM 内看门狗（闲置/硬顶自关）、进程内 LLM 调用配额、$20 预算告警。

---

## 1. 部署前要准备的东西（一次性清单）

开始前把下面这些备齐，部署过程就不会卡：

- [ ] **本机 gcloud 已登录**：`gcloud auth list` 能看到 `yi.xin7319@myunfc.ca`。
- [ ] **仓库已推到 GitHub 且可 clone**（provision 脚本要在 VM 上 clone 它）。
      记下 clone URL：`https://github.com/<owner>/<repo>.git`。
- [ ] **GCP 标识**（从你的私人笔记填；已验证的项目是 "My First Project"）：
      项目 ID、项目编号、计费账户 ID、区（us-central1-a）。
- [ ] **Gmail 应用专用密码**（用于发通知邮件给你自己）：
      Google 账号 → 安全性 → 两步验证 → 应用专用密码，生成一个 16 位密码。
      记下发信 Gmail 地址 + 这个密码。
- [ ] **收件人 token**（每家公司一个，就是"兴趣信号"）：每个用
      `python3 -c "import secrets; print(secrets.token_urlsafe(24))"` 生成，
      记下 `token → 公司名` 的对应表（**只存你私人笔记，绝不进仓库**）。
- [ ] **DEMO_GATE_KEY**（共享访问密钥，VM 与函数必须一致）：
      `python3 -c "import secrets; print(secrets.token_urlsafe(24))"` 生成一个。
      ⚠️ 占位值 `CHANGE-ME-...` 会被应用 fail-closed 拒绝，必须换成强随机值。
- [ ] **.env**（本机仓库根目录已有）：含 `MINIMAX_*` 和 `NEO4J_*`，会 scp 到 VM。

先把标识导入 shell（每个终端会话开头执行一次）：

```bash
export PROJECT=<gcp-project-id>
export PROJECT_NUMBER=<gcp-project-number>
export BILLING=<billing-account-id>
export ZONE=us-central1-a
export REPO_URL=https://github.com/<owner>/<repo>.git
```

---

## 2. 部署步骤

> 每一步都对应 [runbook.md](runbook.md) 的同名小节。逐步执行，不要跳。

### Step 0 — 启用所需 API（一次性）

```bash
gcloud services enable run.googleapis.com cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com --project=$PROJECT
```

Compute / billing-budgets / Gmail 已启用（2026-07-18 核过），这里只补触发函数要的三个。

### Step 1 — 建 VM（默认停机、大内存 CPU）

```bash
gcloud compute instances create learnarken-demo \
  --machine-type=e2-highmem-8 --zone=$ZONE \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced \
  --tags=learnarken-demo --project=$PROJECT
```

- 不用 GPU：GPU 抢手、只能拿 Spot，演示中被抢占 = 面试官面前死机。CPU 慢几秒可接受。
- `pd-balanced` 而非更便宜的 `pd-standard`：冷启动要从磁盘读多 GB 嵌入模型，HDD 会
  让每次等待多几分钟。这是唯一常驻成本项，若想更省可换 standard（代价是更慢的冷启动）。

### Step 2 — 防火墙（只放行 Streamlit 和状态 shim）

```bash
gcloud compute firewall-rules create learnarken-demo-ports \
  --direction=INGRESS --action=ALLOW --rules=tcp:8501,tcp:8110 \
  --target-tags=learnarken-demo --project=$PROJECT
```

后端 FastAPI（8100）、Vespa、Neo4j 全部只绑 loopback，不对外——安全边界与本地一致。

### Step 3 — 在 VM 上 provision（装栈、灌语料、装 systemd）

```bash
gcloud compute ssh learnarken-demo --zone=$ZONE --project=$PROJECT
# 进入 VM 后：
curl -LO https://raw.githubusercontent.com/<owner>/<repo>/main/deploy/vm/provision.sh
sudo bash provision.sh "$REPO_URL"
```

脚本做的事：装 docker/git，建不带 docker 组的 `learnarken` 用户（docker 由 root 单元管，
红队 #11），clone 仓库，`uv sync`，起 Vespa/Neo4j 容器（**已定版**，非 latest），
`learnarken index` 灌 package-a+c 并把嵌入模型拉进缓存（**这一步最慢，只跑一次**），
装 4 个 systemd 单元。脚本会在缺 `.env` 时**停下并提示**——那是下一步。

### Step 4 — 放密钥（缺则 fail-closed，不会误启动）

回到本机：

```bash
# 4a. MiniMax/Neo4j 配置
gcloud compute scp .env learnarken-demo:/tmp/.env --zone=$ZONE --project=$PROJECT
gcloud compute ssh learnarken-demo --zone=$ZONE --project=$PROJECT \
  --command='sudo install -o learnarken -m 600 /tmp/.env /opt/learnarken/LearnArken/.env && rm /tmp/.env'
```

然后在 VM 上把共享密钥填进 `demo.env`（provision 已生成占位版）：

```bash
gcloud compute ssh learnarken-demo --zone=$ZONE --project=$PROJECT
sudo sed -i 's|^DEMO_GATE_KEY=.*|DEMO_GATE_KEY=<你生成的强随机key>|' /opt/learnarken/demo.env
# 若 Step 3 在 .env 检查处停过，现在重跑 provision.sh 收尾
```

### Step 5 — 实测冷启动时长，填回状态页（INV-5：页面数字必须是实测值）

```bash
gcloud compute instances stop learnarken-demo --zone=$ZONE --project=$PROJECT
time ( gcloud compute instances start learnarken-demo --zone=$ZONE --project=$PROJECT && \
  until curl -fsS "http://$(gcloud compute instances describe learnarken-demo \
    --zone=$ZONE --project=$PROJECT \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)'):8110/demo/status" \
    | grep -q '"status": "ready"'; do sleep 5; done )
```

把测得的墙钟时间填进 `deploy/trigger/index.html`（把"ready in a few minutes"改成实测值），
并记进 `docs/discussions/day10.md`。

### Step 6 — 部署触发函数（含 DEMO_GATE_KEY，必须与 VM 一致）

```bash
# 6a. 最小权限服务账号：只能 start/get 实例，不能删、不能 ssh
gcloud iam service-accounts create learnarken-trigger --project=$PROJECT
gcloud iam roles create learnarkenDemoStarter --project=$PROJECT \
  --permissions=compute.instances.start,compute.instances.get,compute.zoneOperations.get
gcloud compute instances add-iam-policy-binding learnarken-demo --zone=$ZONE --project=$PROJECT \
  --member=serviceAccount:learnarken-trigger@$PROJECT.iam.gserviceaccount.com \
  --role=projects/$PROJECT/roles/learnarkenDemoStarter

# 6b. 部署（DEMO_GATE_KEY 与 Step 4 填的完全相同；TOKENS_JSON 是 token→公司 表）
gcloud functions deploy learnarken-demo-gate --gen2 \
  --region=${ZONE%-*} --runtime=python312 \
  --source=deploy/trigger --entry-point=demo_gate \
  --trigger-http --allow-unauthenticated --max-instances=2 \
  --project=$PROJECT \
  --service-account=learnarken-trigger@$PROJECT.iam.gserviceaccount.com \
  --set-env-vars=GCP_PROJECT=$PROJECT,GCP_ZONE=$ZONE,VM_NAME=learnarken-demo,NOTIFY_EMAIL=<你的邮箱>,SMTP_HOST=smtp.gmail.com,SMTP_PORT=465,SMTP_USER=<发信Gmail>,SMTP_PASS=<应用专用密码>,DEMO_GATE_KEY=<与VM相同的key>,TOKENS_JSON='{"<token1>":"<公司A>","<token2>":"<公司B>"}'
```

部署完拿到函数 URL，招聘方的链接就是 `https://<function-url>/?t=<token1>`。

### Step 7 — $20 预算告警（叠加在既有 $200 CAD 账户告警之上）

```bash
gcloud billing budgets create --billing-account=$BILLING \
  --display-name="LearnArken demo fence" --budget-amount=20 \
  --filter-projects=projects/$PROJECT_NUMBER \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
```

### Step 8 — 验收 drill（对齐 SPEC 验收 1–4）

1. 停机 VM，打开 `?t=<token>` 链接 → 页面显示 **closed** + 成本说明。
2. 点启动 → **starting**（真实自检分阶段）→ **running** + 倒计时；点 demo 链接，
   分别问一个预置问题和一个自由问题，确认真栈作答带引用。
3. 确认收到两封邮件（点击通知、就绪通知）。
4. 页面开着挂 30 分钟不提问 → VM 自动关机，页面回到 **closed** + 可再启动。
5. `gcloud billing budgets list --billing-account=$BILLING` 能看到 $20 围栏。

---

## 3. 日常使用（投递时）

- 每家公司发**各自的 token 链接**——这样你能从"谁点了"知道哪家在看（点击会给你发邮件）。
- 想加新公司：改函数的 `TOKENS_JSON` 重新 `gcloud functions deploy`（或用 gcloud 更新
  环境变量），并在私人笔记里加一行 `token→公司`。
- 想停用某个 token：从 `TOKENS_JSON` 删掉再部署。
- **平时保持 VM 停机**——它会因为闲置自动关，你一般不用管。

---

## 4. 排错

| 症状 | 原因 / 处理 |
| --- | --- |
| 打开 Streamlit 显示"需从邀请链接进入" | `?k=` 缺失或与 VM 的 `DEMO_GATE_KEY` 不一致；确认 Step 4 与 Step 6b 的 key 完全相同，且不是占位值 |
| 页面一直 starting 不到 running | 冷启动确实要几分钟（首跑更久）；若超 10 分钟，`gcloud compute ssh` 上去看 `journalctl -u learnarken-demo` |
| demo 链接打不开但页面 running | 外网 IP 每次开机会变——用页面给出的 `demo_url`，别用旧 IP |
| 没收到邮件 | Gmail 应用专用密码/端口(465/SSL)核对；邮件是尽力发，失败不影响页面，`journalctl` 看函数日志 |
| 提问报"reached its daily question limit" | 触发了 LLM 调用配额（默认 200/开机）；重启 VM 重置，或调 `demo.env` 的 `DEMO_MAX_LLM_CALLS` |
| VM 没按时关机 | 看门狗每分钟跑；`systemctl status learnarken-watchdog.timer`、`journalctl -u learnarken-watchdog` |
| 容量报错（起不来 VM） | e2-highmem-8 偶发 stockout，换个 zone（us-central1-b/c）重试 |

---

## 5. 成本与安全须知

- **成本**：停机 ~$4/月（磁盘）；每次演示 ~$0.2；围栏最坏情况（自关全失效跑满 3h 硬顶）
  约 $1.1，$20 告警远早于此触发。
- **已知残留（SPEC Out-of-Scope，非疏漏）**：token 与 key 走 URL（非 cookie）；demo 走
  明文 HTTP。对无敏感输入的作品集 demo 可接受；正式生产需上 TLS + 每人会话鉴权。详见
  [docs/reviews/day10.md](../docs/reviews/day10.md)。
- **绝不进 git**：`.env`、`demo.env`、`TOKENS_JSON` 的真实值、`DEMO_GATE_KEY`、SMTP 密码、
  `token→公司` 对应表（后者属个人求职情报，INV-1 同族红线）。

---

## 6. 停用 / 收尾（求职结束后）

```bash
gcloud functions delete learnarken-demo-gate --region=${ZONE%-*} --project=$PROJECT
gcloud compute instances delete learnarken-demo --zone=$ZONE --project=$PROJECT
gcloud compute firewall-rules delete learnarken-demo-ports --project=$PROJECT
```

预算告警和服务账号可保留或一并删除。删实例后磁盘一起删，月费归零。
