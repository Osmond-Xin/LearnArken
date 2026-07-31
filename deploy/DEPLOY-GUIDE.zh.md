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

- **实际部署机型是 `c3-highmem-8`，不是 `e2-highmem-8`**：2026-07-29 当天 `e2-highmem-8`
  （以及 `n2`/`n2d`）在 us-central1-a 无库存，只能同区换到 `c3-highmem-8`（同为 8 vCPU / 64GB）。
  约 $0.53/小时 vs $0.36/小时，单次演示约 $0.16 而非 $0.11；停机成本不变。**实测的 196 秒冷启动
  以及由它推出的所有常数都是在 c3 上量的**，换机型要重测（二轮红队）。
- **停机时只付磁盘**：100GB pd-balanced 约 **$10/月**（旧稿写的 $4 是 pd-standard 的价格，
  和本指南自己创建的磁盘类型对不上——红队 R-10）；**运行时** e2-highmem-8 约 $0.36/小时，
  一次演示约 $0.18–0.30。
- 三处独立的成本围栏：VM 内看门狗（闲置/硬顶自关）、进程内 LLM 调用配额、$20 预算告警。

---

## 1. 部署前要准备的东西（一次性清单）

开始前把下面这些备齐，部署过程就不会卡：

- [ ] **本机 gcloud 已登录**：`gcloud auth list` 能看到 `yi.xin7319@myunfc.ca`。
- [ ] **仓库已推到 GitHub 且可 clone**（provision 脚本要在 VM 上 clone 它）。
      记下 clone URL：`https://github.com/<owner>/<repo>.git`。
- [ ] **GCP 标识**（从你的私人笔记填；已验证的项目是 "My First Project"）：
      项目 ID、项目编号、计费账户 ID、区（us-central1-a）。
- [ ] ~~**Gmail 应用专用密码**~~ —— **已取消，不需要**（Yi Xin 2026-07-29 决定）：
      投递走 LinkedIn 和网站表格，没有用于发信的邮箱。`SMTP_*` 与 `NOTIFY_EMAIL`
      留空即可，函数里的发信会干净地跳过。**「谁点了」仍然有**，靠的本来就是
      per-recipient token，不是邮件——从函数日志读：
      `gcloud functions logs read learnarken-demo-gate --region=us-central1 --gen2 --limit=50 | grep 'demo link opened'`
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
gcloud services enable compute.googleapis.com run.googleapis.com \
  cloudfunctions.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com billingbudgets.googleapis.com --project=$PROJECT
```

已建项目里 Compute / Artifact Registry / Billing Budgets 通常已开；全新项目六个都要开（红队 R-20）。

### Step 1 — 建 VM（默认停机、大内存 CPU）

```bash
gcloud compute instances create learnarken-demo \
  --machine-type=c3-highmem-8 --zone=$ZONE \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced \
  --tags=learnarken-demo --project=$PROJECT \
  --no-service-account --no-scopes
```

> **2026-07-30 修订**：`--no-service-account` 已不是线上 VM 的现状。为了让访客在
> demo 里做了什么能留下记录，它现在挂了一个只含 `roles/logging.logWriter` 的服务
> 账号——见 Step 9，那里写了这笔交易和理由。新建机器仍从上面这个形态起步。

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

⚠️ 光加这条规则**不等于「只有 8501/8110 对外」**：VPC 默认还有一条 `default-allow-ssh`
（0.0.0.0/0，优先级 65534）把 22 端口开给全世界（红队 R-08）。优先级数字小的先生效：

```bash
gcloud compute firewall-rules create learnarken-demo-ssh-allow \
  --direction=INGRESS --action=ALLOW --rules=tcp:22 --priority=900 \
  --source-ranges=<你的公网IP>/32,35.235.240.0/20 \
  --target-tags=learnarken-demo --project=$PROJECT
gcloud compute firewall-rules create learnarken-demo-ssh-deny \
  --direction=INGRESS --action=DENY --rules=tcp:22 --priority=950 \
  --source-ranges=0.0.0.0/0 --target-tags=learnarken-demo --project=$PROJECT
```

### Step 3 — 在 VM 上 provision（装栈、灌语料、装 systemd）

```bash
gcloud compute ssh learnarken-demo --zone=$ZONE --project=$PROJECT
# 进入 VM 后：
# 用具体 commit，不要跟着 main 漂（红队 R-11）
curl -LO https://raw.githubusercontent.com/<owner>/<repo>/<commit-sha>/deploy/vm/provision.sh
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
# 暂存在自己的家目录而非 /tmp（/tmp 全局可读，别的进程能看着它出现——红队 R-13）
gcloud compute scp .env learnarken-demo:~/.env.staged --zone=$ZONE --project=$PROJECT
gcloud compute ssh learnarken-demo --zone=$ZONE --project=$PROJECT \
  --command='sudo install -o learnarken -m 600 ~/.env.staged /opt/learnarken/LearnArken/.env && shred -u ~/.env.staged'
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
  --permissions=compute.instances.start,compute.instances.get,\
compute.instances.setLabels,compute.zoneOperations.get
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
  --set-env-vars=GCP_PROJECT=$PROJECT,GCP_ZONE=$ZONE,VM_NAME=learnarken-demo,DEMO_GATE_KEY=<与VM相同的key>,TOKENS_JSON='{"<token1>":"<公司A>","<token2>":"<公司B>"}'
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
3. 从函数日志确认点击被记录（不再有邮件）：
   `gcloud functions logs read learnarken-demo-gate --region=us-central1 --gen2 --limit=50 | grep -E '打开|demo link opened|VM start issued'`
4. 页面开着挂 30 分钟不提问 → VM 自动关机，页面回到 **closed** + 可再启动。
5. `gcloud billing budgets list --billing-account=$BILLING` 能看到 $20 围栏。
### Step 9 — 访客日志：看清访客在 demo 里做了什么（2026-07-30 新增）

**背景**：2026-07-30 有真实访客（Nova Scotia 的 Bell 家宽，不是你自己的网络）点开
`arken-web-form` 链接、按了启动、VM 跑满 34 分钟自关。而这次访问留下的全部记录只有
函数日志两行：`demo link opened` 和 `VM start issued`。他有没有提问、问了什么、被不被
拒答——全都不知道，因为 demo 自己的日志写在 journald 里，随关机一起消失；而且成功的
`/query` 以前根本不写日志，只有失败才写。

**代价说清楚**：这一步推翻了 Step 1 的 `--no-service-account`。VM 从此有身份，被 RCE
就等于交出一个 token——但这个 token 只能做一件事：往本项目写日志。读不了数据、开不了
机器、碰不了账单。现实滥用是刷日志，成本是 Cloud Logging 摄入（每月前 50 GiB 免费，
一次 30 分钟会话只有个位数 MB），且 $20 预算告警照样在上面兜着。

```bash
# 9a. 只能干一件事的服务账号
gcloud iam service-accounts create learnarken-demo-vm \
  --display-name="LearnArken demo VM (logging only)" --project=$PROJECT

VM_SA=learnarken-demo-vm@$PROJECT.iam.gserviceaccount.com
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$VM_SA" --role=roles/logging.logWriter

# 9b. 挂上去（VM 必须处于停机状态；scope 用最窄的 logging.write，不给 cloud-platform）
gcloud compute instances set-service-account learnarken-demo --zone=$ZONE \
  --service-account=$VM_SA \
  --scopes=https://www.googleapis.com/auth/logging.write --project=$PROJECT

# 9c. 开一次机：把 VM 切到评审过的 commit、装 agent、重启应用
#     SHA 必须已经在 origin 上——VM 是从那儿 fetch 的
gcloud compute instances start learnarken-demo --zone=$ZONE --project=$PROJECT
SHA=<合并后的 commit>
gcloud compute ssh learnarken-demo --zone=$ZONE --project=$PROJECT --command "
  set -e
  REPO=/opt/learnarken/LearnArken
  sudo -u learnarken git -C \$REPO fetch origin $SHA
  sudo -u learnarken git -C \$REPO checkout --detach $SHA
  test \"\$(sudo -u learnarken git -C \$REPO rev-parse HEAD)\" = '$SHA'
  # root 跑的是 git 在那个 commit 哈希下存的字节，而不是工作区里恰好是什么
  sudo -u learnarken git -C \$REPO cat-file blob $SHA:deploy/vm/install_ops_agent.sh \
    | sudo tee /usr/local/sbin/learnarken-install-ops-agent >/dev/null
  sudo chown root:root /usr/local/sbin/learnarken-install-ops-agent
  sudo chmod 755 /usr/local/sbin/learnarken-install-ops-agent
  sudo /usr/local/sbin/learnarken-install-ops-agent
  sudo systemctl restart learnarken-demo"
```

这一步有三个坑（是查了线上 VM 的真实状态才发现的，不是猜的）：

- **仓库是 detached 状态、属主是 `learnarken`**（provision 按 SHA 钉住，红队 R-11）。
  `sudo git pull` 会错两次：detached HEAD 没有上游分支；root 去动别人的仓库会触发
  git 的 dubious-ownership 保护。要像 `provision.sh` 那样以 `learnarken` 身份 fetch。
- **root 不能凭信任去执行那个目录里的文件**：以 `learnarken` 身份攻陷 VM 的人可以改写
  `install_ops_agent.sh`，等下一次操作者 `sudo bash` 它——这等于 runbook 亲手递上一条
  提权路径（二轮红队 P2）。所以 root 执行的是 **git 在那个 commit 哈希下存的 blob**，
  拷到 root 自己的路径再跑：要伪造它得先伪造一次 SHA-1 碰撞，改工作区没有用。

  这一步的第一版是断言 `git status --porcelain` 为空。**它在这台机器上永远不可能通过**：
  线上 VM 的工作区里有十几个未跟踪的 macOS `._*` 文件，是 2026-07-29 从 Mac `scp`
  部署文件时带过去的。这是 2026-07-31 真跑了一遍才发现的，不是读出来的。
- **光装 agent 没用**：要送的那两行日志是新后端代码写的，所以 VM 必须切到新 commit
  **并重启** `learnarken-demo`。顺序是先装 agent 后重启，这样应用的第一行输出就被收走。
- **commit 得先在 `origin` 上**：分支没合并推上去之前，VM 无处可 fetch。

装完不用管，30 分钟闲置看门狗会自己关机（也可手动 `instances stop`）。

**以后怎么查（不用开机）**：

```bash
# 访客问了什么、结果如何
gcloud logging read 'resource.type="gce_instance" AND jsonPayload.event="demo_query"' \
  --limit=50 \
  --format="value(timestamp,jsonPayload.turn,jsonPayload.outcome,jsonPayload.question)" \
  --project=$PROJECT

# 是点的推荐问题还是自己打的
gcloud logging read 'resource.type="gce_instance" AND jsonPayload.event="demo_entry"' \
  --limit=50 --format="value(timestamp,jsonPayload.turn,jsonPayload.source)" --project=$PROJECT
```

每条日志的正文**就是一个 JSON 对象**：问题里带换行伪造不出第二条记录，而且筛选走
`jsonPayload.event` 字段，不是访客能在提问里打出来的子串。`turn` 把同一轮的两条串起来。
两条都只在 `DEMO_PUBLIC=1` 下才写，本地 `make demo` 和测试套件一行都不产。

读之前要知道的三件事：

- **这是遥测，不是审计**：日志由 VM 用自己的凭据写，所以能控制 VM 的人也能写。可信的
  那一半是 Cloud Audit Logs（谁启的机、来自网关函数）；`demo_query` 只代表"demo 自己
  说发生了这件事"。
- **整个 journal 都会上传**，不只这两行——sshd、systemd、容器都在内。这是有意的（demo
  出问题事后要能查），也正因如此保留期很重要。2026-07-30 实测：线上这版 Streamlit 根本
  不打请求日志，所以 `?k=` 密钥不会从这条路进 journal。
- **成本在量上**：每月前 50 GiB 摄入免费，一次 30 分钟会话只有个位数 MB；但被攻陷的 VM
  可以一直写到 $20 预算告警响。那个告警就是唯一的围栏。

日志进 `_Default` 桶，按其保留期（默认 30 天）过期——真有价值的访问记录请自己拷出来存。


---

## 3. 日常使用（投递时）

- 每家公司发**各自的 token 链接**——这样你能从"谁点了"知道哪家在看（点击记在函数日志里）。
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
| 想知道谁点了 | 不再走邮件；看函数日志里的 `demo link opened by recipient=…`，对照你私人笔记里的 token→公司 表 |
| 想知道访客在 demo 里做了什么 | Step 9 的两条日志：`demo query`（问了什么、答/拒/错、耗时）与 `demo entry`（点推荐还是自己打）；VM 停机也能查 |
| 提问报"reached its daily question limit" | 触发了 LLM 调用配额（默认 200/开机）；重启 VM 重置，或调 `demo.env` 的 `DEMO_MAX_LLM_CALLS` |
| VM 没按时关机 | 看门狗每分钟跑；`systemctl status learnarken-watchdog.timer`、`journalctl -u learnarken-watchdog` |
| 容量报错（起不来 VM） | e2-highmem-8 偶发 stockout，换个 zone（us-central1-b/c）重试 |

---

## 5. 成本与安全须知

- **成本**：停机 ~$10/月（100GB pd-balanced 磁盘）；每次演示 ~$0.2；围栏最坏情况（自关全失效跑满 3h 硬顶）
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
gcloud iam service-accounts delete \
  learnarken-demo-vm@$PROJECT.iam.gserviceaccount.com --project=$PROJECT
```

预算告警和服务账号可保留或一并删除。删实例后磁盘一起删，月费归零。
