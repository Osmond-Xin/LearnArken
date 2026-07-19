# Day 10 设计讨论蒸馏 — 部署选型（按需真栈）

> **AI-distilled**（Claude 实现方，2026-07-18，同 session 蒸馏；INV-6：AI 蒸馏、
> 标注、待 Yi Xin 复核）。来源：handoff day9 §6 的张力清单 + DR 报告
> `day10-AI Demo 部署与展示.md` + Yi Xin 2026-07-18 的两轮口述裁定 + 实现方
> 当日比价/触发机制调研。格式：问题 → 选项 → 决定 → 理由。**部分项仍开放**，
> 决策层权威以 Yi Xin 手写的 `docs/specs/day10.md` 为准。

## D1 部署哲学：免费层切片 vs 按需真栈

- **问题**：本 app（Vespa + Neo4j + 本地 8B/bge 模型 + MiniMax）无法整体上免费层。
  handoff 摆了 A（预计算+进程内简化切片）/ B（托管服务）/ C（罐装）三条路，A 还
  内含「查询侧 embedding 用什么」的子选择（Qwen3-8B 跑不进免费层 16GB CPU 容器，
  换 bge-m3 则与 EVIDENCE.md 基准口径漂移，须 INV-5/INV-7 标注）。Yi Xin 补充
  关键事实：**预期完全没有自然流量**，且手上有 AWS/GCP 付费账户 + Vercel。
- **选项**：(a) A（HF Spaces 免费层 + bge-m3 换口径 + 诚实标注）；(b) **D：按需
  真栈**——停机 VM 装本地同款 docker-compose（`make demo` 原样），常驻免费触发器
  按需开机，闲置自动关机；(c) E：Cloud Run scale-to-zero（Vespa/Neo4j 塞
  sidecar，工程别扭）；(d) F：纯静态+人工联系启动。
- **决定（Yi Xin，2026-07-18）**：**D 定案，不再做 A**。展示分两层：第 0 层
  永远在线的静态门面（README/门面页：架构图 + demo GIF + EVIDENCE.md），第 1 层
  对方触发的按需真栈。
- **理由**：零流量前提下，常驻免费切片的「口径漂移 + 玩具后端」代价换不来价值；
  按需真栈**跑的就是 EVIDENCE.md 同口径的完整栈**，零 INV-5 caveat、零「替代
  后端」标注。触发即兴趣信号（求职漏斗埋点），冷启动等待期转化为讲架构图的控场
  时间（DR §5 剧本）。scale-to-zero + 费用围栏本身是比免费层玩具更强的面试叙事。

## D2 云平台：AWS vs GCP 比价（同规格 8 vCPU / 64GB）

- **问题**：Yi Xin 两个付费账户都在手，裁定规则=「相同部署哪个便宜用哪个」。
- **调研（实现方，2026-07-18 报价，us 区）**：
  | 项 | AWS | GCP |
  | --- | --- | --- |
  | VM 8 vCPU/64GB | r6a.2xlarge **$0.454/hr** | e2-highmem-8 **$0.3616/hr**（便宜 ~20%） |
  | 单次启动 30 min | ~$0.23 | ~$0.18 |
  | 磁盘 100GB/月（停机期唯一常驻成本） | gp3 ~$8 | pd-balanced ~$10 / pd-standard ~$4 |
  | 触发函数 | Lambda 免费额度内 | Cloud Functions 免费额度内 |
  | 邮件件 | **原生**（SNS 通知自己零配置；SES 发外人需出 sandbox） | **无原生邮件**，需 Gmail SMTP / SendGrid 等第三方 |
- **决定（Yi Xin，2026-07-18 第三轮）**：**GCP 定案**，用本机 gcloud 已指向的
  「My First Project」（`project-4a8f355b-f36e-4cf2-990`，可直接花钱）。
- **本机可部署性验证（AI，2026-07-18，只读检查全过）**：
  - gcloud 567.0.0 在（`/opt/homebrew/bin/gcloud`），账号 `yi.xin7319@myunfc.ca`
    已认证；默认 region/zone = **us-central1/-a**（与比价同区）。
  - 项目 ACTIVE、**billingEnabled: true**；`compute instances list` 可操作（现 0 台）。
  - 配额（us-central1）：E2_CPUS 24 / CPUS 200 / 磁盘 4TB / 在用 IP 8——
    e2-highmem-8（8 vCPU）富余。
  - 已启用 API：compute、**billingbudgets**（$20 告警可直接建）、artifactregistry、
    gmail、monitoring/logging。**未启用：run / cloudfunctions / cloudbuild /
    cloudscheduler**——触发函数部署前需 `gcloud services enable`（一条命令，
    Day 10 实施步骤，不提前动）。
  - 项目挂在 organization 下（myunfc.ca），已核组织策略：
    `compute.vmExternalIpAccess` = **ALLOW 全部**，外网 IP 不被禁，demo 可行。
- **理由**：同规格便宜 ~20%、磁盘可用 pd-standard 更省、Gmail 通道免 SES sandbox；
  本机 CLI 链路验证可直接部署，无迁移成本。

## D3 触发开关形态：token 静态页 = 导览 + 状态机

- **问题**：对方如何触发启动、双方如何得知就绪、点了就走的人回来看到什么。
- **决定（Yi Xin，2026-07-18 第二轮，形态完整定案）**：
  - 邮件里附**带特殊 token 的 URL**；点击落到一个**静态页**（不是直接开机跳转）。
  - 静态页双目的：①**项目导览**——架构图 + 关键点说明，引导对方理解项目；
    ②**后台状态监控**——实时显示启动进度**与自检（self-check）程度**。
  - 后台启动完毕**且自检通过**后，页面给出完整就绪通知，**并显示倒计时**：
    告知还有多久会自动关闭。
  - 页面任何时刻都显示后台所处状态：**启动中（执行） / 运行中（闲置倒计时） /
    已关闭**。若已关闭，页面提供**再次启动**入口，并诚实告知：「出于费用考虑，
    闲置 30 分钟后自动关闭」。
  - 设计动机：避免「点了→离开→半小时后回来页面空无一物」的死局——对方任何
    时刻回来都能看懂现状、都有下一步动作。
  - 点击时**通知 Yi Xin**（含 token 归属 = 哪家公司点的）；就绪邮件发 Yi Xin 自己。
- **实现要点（AI 起草，进 SPEC 细化层）**：
  - 状态双来源：VM 停机时由**触发函数**用 compute API 报告实例态（函数常驻免费，
    页面轮询它）；VM 起来后由 VM 上的**自检端点**报告应用态——自检直接复用
    `make demo` 的 preflight（fail-closed，INV-4），等于把 fail-closed 公开展示。
  - 倒计时 = 闲置倒计时，与 D4 的 30 分钟同一时钟：每次真实请求重置，页面注明
    「提问会重置倒计时」。
  - 再次启动复用同一 token，受 D4 限频约束。
  - 停机 VM 无固定 IP：就绪时页面下发本次 demo 地址，省静态 IP ~$3.6/月。
- **状态**：**形态定案**；细化层（轮询间隔、自检项清单、页面文案）AI 草拟进 SPEC。

## D4 关机与费用围栏

- **决定（Yi Xin，2026-07-18）**：**30 分钟闲置自动关机** + 成本围栏，**$20 告警**。
- **实现要点（AI 起草，进 SPEC 细化层）**：闲置判定基于 FastAPI 最后请求时间戳，
  关机逻辑**在 VM 内部**（cron/systemd timer 自关）不依赖外部服务——外部失联时
  fail-closed 到关机；云端预算告警 $20/月兜底；触发限频（同 token 每小时一次）。

## D5 VM 规格：大内存 CPU，不用 GPU

- **决定（Yi Xin，2026-07-18）**：**大内存 CPU 机**（64GB，跑 Qwen3-8B 查询嵌入 +
  bge 系 + Vespa + Neo4j）。**不用 GPU**：GPU 机型抢手，大概率只能拿 Spot，
  demo 场景被抢占 = 面试官面前死机，不可接受；CPU 上单条查询嵌入慢几秒可接受。
- **备注**：若实测 8 vCPU 嵌入延迟不可接受，升 16 vCPU（e2-highmem-16
  ~$0.72/hr）是细化层调参，不改架构。

## 淘汰记录

- **A（免费层简化切片）**：D1 裁掉——口径漂移 + 玩具后端，零流量下不值。
- **B（Qdrant Cloud + Aura 托管）**：多账号/密钥面/延迟，对 43 chunks/11 节点
  无意义，且 embedding 换 API 与基准不同源（INV-5 caveat）。
- **C（纯罐装）**：单独用太死；其「预置问题缓存」思想可被 demo 页吸收（细化层）。
- **E（Cloud Run 塞真栈）**：多服务塞 sidecar + 冷启动拉多 GB 模型，工程量高于
  停机 VM 而保真度更低。
- **F（纯静态+人工启动）**：反馈链路以小时计，错过 DR 说的 ~3 分钟评审窗口。
  其「架构图常驻」部分已并入 D1 的第 0 层。

## 未决清单（进 SPEC 前需 Yi Xin 拍）

1. demo 页预置问题缓存、MiniMax 实时调用的限流策略（C 的遗产，细化层可 AI 草拟）。
