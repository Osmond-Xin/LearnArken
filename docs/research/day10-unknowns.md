# Day 10 未知点扫描 — 按需真栈部署（on-demand real-stack demo）

> **AI-generated**（Claude 实现方，2026-07-18，步骤 1c 扫）。交叉引用：DR 报告
> [day10-AI Demo 部署与展示](../gemini-deepresearch/day10-AI%20Demo%20部署与展示.md)、
> [tutorials/12](../tutorials/12-interview-prep.md)、
> [docs/discussions/day10.md](../discussions/day10.md)（D1–D5 裁定）。
> 注意：DR 报告的选型前提（免费层 HF Spaces/Streamlit CC）已被 Yi Xin 的 D1 裁定
> **推翻**（按需真栈,付费 GCP）——报告的平台对比章节按「已淘汰选项的背景知识」读，
> 其防滥用/降级/README/口述章节仍然有效。

## 张力清单（T1–T8）

### T1 「闲置」的定义决定看门狗是否形同虚设

30 分钟闲置关机（D4）的前提是能判定「闲置」。坑：Streamlit 前端对后端可能有
**周期性心跳/轮询**（websocket keepalive、`st.rerun`），状态页也要轮询自检端点——
若把「任何 HTTP 请求」都算活动，**闲置永远不会发生**，围栏失效、钱一直烧。
**裁法（细化层）**：活动 = 业务端点调用（`/answer`、`/search`、`/graph` 等），
健康/自检/状态轮询**明确不算**；倒计时页面展示的就是这个业务时钟。

### T2 自检端点是公开面，不能变成泄露面

状态页要展示「自检程度」（D3），意味着 preflight 结果要暴露到公网。坑：preflight
输出可能含内部路径、依赖版本、配置细节。**裁法**：公开端点只给**阶段枚举 +
布尔**（vespa: ok / neo4j: ok / models: loading / llm: ok），详情留 VM 日志。
Day 9 教训（[[security-fence-self-review-blindspot]]）：这个端点自身就是新的
信任边界入口，红队时按入口清单枚举。

### T3 token 即凭证：URL 里的东西会被转发

邮件里的 token URL 会被收件人转发、进邮件网关日志。风险接受度：token 只能
**开机**（花的钱有围栏封顶），不能读数据、不能改配置——最坏滥用 = 频繁开机，
被限频（每 token 每小时一次）+ $20 告警 + 30 分钟自关兜底。**裁法**：token
可撤销（函数侧配置列表）；状态页零外链（无 referrer 泄露面）；token 列表与
映射（token→公司）**绝不进仓**（INV-1 同族红线：求职情报是个人数据）。

### T4 冷启动时长是未测数字，页面进度必须诚实

e2-highmem-8 上 `docker compose up` + Qwen3-8B 从磁盘载入 64GB RAM + Vespa
喂 43 chunks + Neo4j 起图——**总时长没实测过**（估 3–6 分钟，其中模型载入占大头）。
INV-5 纪律：页面上显示的预估时长必须来自**实测**（部署日实测一次，写进配置），
不能拍脑袋写「约 2 分钟」。进度分阶段展示（实例启动→容器起→模型载入→自检→就绪），
每阶段由自检端点真实上报，不做假进度条。

### T5 VM 磁盘上有 MiniMax key：密钥面从仓库移到了云

`.env`（`MINIMAX_*`）要到 VM 上才能跑生成。选项：(a) 直接放 VM 磁盘（简单，
磁盘即信任边界，项目私有）；(b) Secret Manager + 启动时拉取（更正规，多一个
API）。倾向 (a) + 磁盘不做镜像共享，(b) 记 Roadmap。**无论哪种，key 永不进
git**（INV-1）；demo 的 MiniMax 调用要有输入长度拦截 + 会话限流（DR §2 的
预算暴露警告）。

### T6 围栏的失效模式要闭环

看门狗是 VM 内 cron/systemd（D4：外部失联也能自关）。坑：看门狗自身挂了怎么办？
**层次**：①看门狗（30 min 闲置）→②硬上限（无论活动与否，开机 N 小时强制关，
防「有人挂机刷活动」）→③$20 预算告警（月度兜底）→④$200 CAD 账户级告警（已存在）。
①②在 VM 内，③④在云端，互相独立。这个分层本身是面试素材（fail-closed 的
成本版）。

### T7 与 execution-plan 的显式偏离要留痕

execution-plan §Day 10 写的是「Streamlit Community Cloud 或 HuggingFace
Spaces」。D1 裁定（按需真栈）是**人裁偏离**：零流量前提 + 付费账户在手 +
真栈零口径漂移优于免费层玩具切片。SPEC 决策层记录此偏离及理由；execution-plan
本身不改（历史文档）。

### T8 裸 IP + HTTP 的观感与安全边界

停机 VM 每次开机拿临时 IP，demo 地址形如 `http://<ip>:8501`——无 HTTPS。浏览器
会标「不安全」，观感打折。选项：(a) 接受 + 页面说明（demo 无敏感输入）；
(b) nip.io + Caddy 自动证书（Let's Encrypt 对 nip.io 有限速风险）；(c) 固定域名
（超范围）。倾向 (a)，(b) 时间富余再做。注意：**不在 demo 页收集任何用户输入
之外的数据**，输入框有长度上限。

## 必须吃透的点（must-master）

1. **GCE 生命周期与计费**：`TERMINATED`（停机）状态只付磁盘/IP，不付 vCPU/RAM；
   `instances start` 秒级返回但 guest boot + compose 需分钟级；临时 IP 每次
   开机变化。这是整个 D 方案的成本模型基础。
2. **Cloud Functions gen2 = Cloud Run**：HTTP 触发、需启用 run/cloudfunctions/
   cloudbuild；用服务账号最小权限（`compute.instances.start/get` + 无删除权）。
   函数是**常驻免费触发器 + 停机期状态源**（compute API 报实例态）双职。
3. **systemd timer vs cron**：看门狗用 systemd timer（`OnUnitActiveSec`），
   崩溃自动重启、日志进 journald;比 crontab 可观测。
4. **HF 模型缓存离线化**：`HF_HUB_OFFLINE=1` + 预热下载进磁盘镜像，避免每次
   开机重新拉多 GB(拉一次 = 分钟级 + 出口流量费)。
5. **Gmail 发信通道**：Cloud Function 里用 Gmail API（项目已启用）或 SMTP
   app password;二选一在实施时定,通知仅发 Yi Xin 自己（无 SES sandbox 类问题）。
6. **DR §5/§6 仍然生效的部分**：评审 3 分钟窗口 → 第 0 层静态门面必须自足；
   预置问题缓存答案（零 API 费）；输入拦截防 400/费用打穿；移动端适配。

## 盲区四象限（Anthropic "Finding Your Unknowns"）

- **知道自己知道**：gcloud 链路已验证（D2）;compose 栈本地天天跑（`make demo`）。
- **知道自己不知道**：冷启动实测时长（T4）;e2 共享核上 8B 嵌入的单条延迟
  （D5 备注:慢几秒可接受,超了升 16 vCPU）。
- **不知道自己知道**：INV-4 fail-closed 语义与「已关闭/拒绝服务」页面态同构——
  Day 5 起的老资产直接复用到状态机文案。
- **不知道自己不知道**（红队重点）：组织策略里除 vmExternalIpAccess 外未逐一核
  的约束（如防火墙默认拒、服务账号建 VM 权限）;Gmail API 发信配额/授权路径;
  us-central1 e2-highmem-8 的可用容量（stockout 罕见但存在）。
