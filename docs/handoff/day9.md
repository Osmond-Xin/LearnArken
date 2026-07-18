# Day 9 会话交接（Handoff）— 2026-07-18

> **AI-generated**（Claude 实现方，session 结束前交接）。目标读者:下一个 AI
> session + Yi Xin。范围:Day 9 已完成部分、Day 10 启动,**重点为 Yi Xin 点名的
> 「部署讨论」备料**。规则源:CLAUDE.md 与 docs/constitution.md。**权威细节以各
> 文档为准,勿仅凭本文摘要行动。**

## 0. 一句话状态

Day 9（证据链与机器可读性）**已完整收口**:实现 + 跨宿主红队全修 + 人裁决 + 提交
打 tag。**单 commit `2a7e034` squash-ff 入 `main`、tag `v0.9.0`、已 push origin
（Yi Xin 执行)、进度表中英双 ✅**。295 测试 + 9 skip 全绿,lint 干净,工作树干净,
`main` 与 origin 同步。**Day 9 结束,下一步 Day 10 = 上线与收尾（`v1.0.0`,最后一天)。**

## 1. Day 9 交付了什么

| 交付物 | 位置 | 要点 |
| --- | --- | --- |
| 证据链 | `docs/EVIDENCE.md` | 抽象能力声明→仓库证据→复跑命令映射表;**INV-1 干净**(不含简历原文,简历留 `resume-master/` 私档反指);诚实分层 Implemented/Toy-scale/Planned |
| AI 协作说明 | `docs/AI-COLLABORATION.md` | 七步日循环 + 红队/裁决样例 + 「哪些必须人做」+ **adversarial validation 双义术语卡**(ML 分布偏移 vs governed-AI 认知/执行分离);说明 CLAUDE.md 行 agents.md 之实 |
| 仓库导览 | `llms.txt`(根目录) | AnswerDotAI 标准;干瘪无营销;相对路径;指 EVIDENCE.md 为「复跑任意数字」入口 |
| 依赖图影响查询 | `src/learnarken/graph/store.py` `impact()` + CLI `graph impact <DMC>` | 反向 dmRef **逐跳 BFS**(非变长 `REFS*`)——防路径爆炸 DoS;访问集去重防 VIO-7 环;限深 + 结果上限;fail-closed;`exists_in_corpus` vs `exists_as_reference` 二分;ADR-0002 接口①并联选型,**不进主 answer pipeline** |
| 证据防漂移测试 | `tests/test_day9_evidence.py` | 死链 + **repo 内边界(INV-1)** + pinned 数字一致 + **未注册数字守卫** + 图 BFS/方向/环/fail-closed(全 hermetic 假传输,脱 Neo4j 也跑) |
| 决策链 | `docs/specs/day9.md`、`docs/discussions/day9.md` | 决策层转录 Yi Xin 口述 + 三裁定(T1 简历/INV-1、T3 图切片、T2 防漂移);细化层 AI 起草 |
| 流程闸产出 | `docs/research/day9-unknowns.md` | 研(在档)→扫(T1–T6) |
| 红队 + 裁决 | `docs/reviews/day9.md` | Part 1(Codex `DO_NOT_MERGE`,10 条)+ Part 2(Yi Xin 签「全部修改」+ 授权 merge) |
| 验收件 | `eval/results/day9-acceptance.json` | MiniMax 只读 llms.txt+EVIDENCE.md 秒级定位复跑命令 |
| 人写 | `docs/journal/day9.md` + day2–8 表头修 | AI 不碰 journal(INV-6) |

## 2. 核心设计（面试级,务必记住）

1. **机器可读性 = 招聘方 AI agent 的简历**:三受众分离——README 给人、`llms.txt`
   给外部检索 agent(静态快照)、`CLAUDE.md` 给仓内协作 agent(行为宪法)。
   EVIDENCE.md 把「每个数字→冻结 artifact→复跑命令」显式索引化,兑现 DR 的「容器
   谬误」破法(指令级证据,不贴图)。验收:陌生 agent(MiniMax)只读两文件即定位复跑。
2. **图影响查询用 BFS 不用变长路径**:红队 P1——`REFS*1..N` 会枚举全部 trail,
   稠密/环图 DoS。改**逐跳 BFS + 访问集**:一跳一查、天然防环、never 枚举整路径,
   限深 + `MAX_IMPACT_RESULTS` 双界。这是 INV-2「as-if-distributed 有界」的兑现。
3. **守卫自身要按它保护的不变量自测**:死链守卫本意护 INV-1,却漏查「链接是否在
   repo 内」——`../resume-master/…` 会通过。红队(Codex)补上。已修:强制
   `relative_to(REPO_ROOT)`。(教训入记忆,见 §7。)
4. **抽象层让部署可换后端**:检索/图都在 `vespa/store.py`、`graph/store.py` 后面
   (INV-2),换索引后端 = 改一个模块,不是重写。**这是 Day 10 部署的关键杠杆**(见 §6)。

## 3. git / tag 状态（勿重做）

- 单 commit `2a7e034 feat(day9): …(v0.9.0)`,squash-ff 入 `main`(无 PR,Yi Xin
  Part 2 授权 direct commit/merge)。含 Day 9 全部交付 + 人写 journal/Part2。
- tag **`v0.9.0`** 打在 `2a7e034`(annotated);`main` 与 tag **已 push origin**。
- `feat/day9` 分支已删(一天一分支)。`pyproject version` 仍 `0.2.0`(历史与 tag
  解耦,沿旧惯例)。
- 验证:`make test`(295+9)、`make lint`;图查询 `learnarken graph impact <DMC>`
  (需 Neo4j)。

## 4. 环境事实（新 session 无需重建）

- **Vespa**:`learnarken-vespa`,`127.0.0.1:8080/19071`。语料 43 chunks(package-a+c)。
- **Neo4j**:`learnarken-neo4j`,`127.0.0.1:7474/7687`。图 11 DM 节点。⚠️ `.env`
  **含 `NEO4J_USER`+`NEO4J_PASSWORD`**(旧 handoff 说「只有 MINIMAX_*」不准,已核;
  `graph/store.py` 读它们,有 fallback)。
- **LLM**:MiniMax（`.env` `MINIMAX_*`),`learnarken.llm.minimax.chat_json`。
  **无 `minimax` CLI**;验收走项目 config。大 context 首跑可能卡(曾 10min),杀掉
  重跑单问即秒级——非通道故障。
- **裁判 CLI**:`codex`(红队闸,exec read-only)、`agy`;`gemini` CLI 已死。
- **模型缓存**(~/.cache/huggingface,SHA pin):Qwen3-Embedding-8B、bge-m3、
  bge-reranker-v2-m3。机器 M5 Max/64GB。
- **demo 拓扑**(部署关键,见 §6):`demo/streamlit_app.py`(**瘦客户端**,只 `requests`
  打 `127.0.0.1:8100`)→ `src/learnarken/api/app.py`(**FastAPI 后端,重**:依赖
  Vespa+Neo4j+本地 8B 模型+MiniMax)。`make demo` = preflight(fail-closed) + 二者。

## 5. backlog / 未办尾巴

- Day 8 遗留(已入 README Roadmap Planned):数字/单位感知匹配、裁判熔断、index
  content-hash/epoch、trace 明文 payload。
- Day 9 红队 #10(localhost 凭证):pre-existing,已文档化,无 Day 9 动作。
- **Day 10 是最后一天**;整切片 DoD 见 execution-plan「完成定义」(10 tag/release
  notes/SPEC/裁决/journal;README 定稿;在线 demo 可访问;60 秒陈述脱稿)。

## 6. Day 10 启动 —— **部署讨论备料（Yi Xin 点名:选型 / 降费 / 怎么部署)**

> **这是本 handoff 的重点。以下是把讨论摆开的「张力清单 + 选项空间」,不是决策——
> Day 10 SPEC 决策层仍由 Yi Xin 手写(INV-6)。我给了倾向性建议,但明确标为「待讨论」。
> 先走每日循环:研报在档 `docs/gemini-deepresearch/day10-AI Demo 部署与展示.md`
> (无需重跑);学 = tutorials/12 §口述关;AI 写 `docs/research/day10-unknowns.md`;
> 再等 Yi Xin 手写 `docs/specs/day10.md`。**

### 6.1 中心约束（讨论的起点)

**本 app 不能整体 lift-and-shift 到任何免费层。** 瘦客户端(Streamlit)轻,但
**FastAPI 后端要 Vespa + Neo4j 容器 + 本地 Qwen3-8B/bge 模型(多 GB,吃显存)+
MiniMax API**。免费层(Streamlit Community Cloud / HF Spaces 免费 CPU)**跑不动
Vespa/Neo4j/8B**。所以部署的真问题不是「传哪」,而是**「部署什么样的简化切片」**。

### 6.2 选型三条路（架构 ×平台,待 Yi Xin 拍)

| 方案 | 做法 | 成本 | 诚实度/风险 |
| --- | --- | --- | --- |
| **A 预计算 + 进程内**（我倾向讨论起点) | 离线把 43-chunk **静态语料**嵌入、向量存文件;运行时用 **NumPy 暴力 cosine**(43 条向量,毫秒)替 Vespa、**内存图**(11 节点,dict/networkx)替 Neo4j;MiniMax API 留作生成(或缓存定问答案) | **近乎零**(免费 CPU 层即可) | 高:检索数学不变,只换索引后端——正是 INV-2 抽象层预留的;**须 INV-7 标注**「在线 demo 用 NumPy/内存后端,非 Vespa/Neo4j」 |
| **B 托管服务** | Qdrant Cloud 免费 + Neo4j Aura 免费 + 托管 embedding API | 低但要多账号;embedding 换 API → **与 EVIDENCE.md 的 Qwen3-8B 基准不再同源(INV-5 caveat)** | 中:更「真」,但引入延迟/漂移/密钥面 |
| **C 前端 + 罐装** | Streamlit 只读跑冻结 artifact / 预录交互 | 最低 | 最诚实(toy),但最不「活」 |

**为什么 A 值得作起点**:语料**又小又静**,预计算是合法简化(不是藏能力),且换后端
是**有界改动**(改 `vespa/store.py`/`graph/store.py` 一处),抽象层现成——这本身是卖点。

### 6.3 降费杠杆（讨论清单）

- 语料小 + 静态 → **离线预计算 embedding、随仓发向量文件**,运行时零 GPU、零向量库。
- 43 chunks → NumPy 暴力检索毫秒级,**生产不需要 Vespa**;11 节点 → 内存图,**不需要
  Neo4j Aura**。
- 唯一不可免的运行时成本 = **LLM 生成(MiniMax API 按调用计费)**。杠杆:demo 固定
  问题集**缓存答案**、限流、「自带 key」输入框、或换免费层小模型。
- 平台免费层**会休眠**——portfolio demo 可接受;**避免常驻付费**。

### 6.4 怎么部署（机制清单）

- **密钥**:`MINIMAX_API_KEY` → 平台 secret store,**永不进仓**(INV-1)。
- **平台细节**:Streamlit Community Cloud(连 GitHub、`requirements`/依赖组、
  secrets、主文件、公开仓、资源上限、休眠) vs HF Spaces(Streamlit/Gradio SDK、
  secrets、硬件选择、可持久)。研报 `day10-AI Demo 部署与展示.md` 有细节,Yi Xin 读。
- **诚实标注(INV-7)**:demo 页 + README 明标「在线切片用 X 替 Y」,哪些是同一数学、
  哪些是替代后端;**基准数字仍指 EVIDENCE.md**(在线 demo 是定性演示,数字留冻结件)。
- **INV-5**:别把「在线 demo 能跑」说成「= 基准数字」——若后端换了(方案 B),明标口径差异。

### 6.5 Day 10 其余交付（execution-plan §Day 10)

- README 定稿:demo GIF、完整基准表、架构图(复用 `docs/diagrams/rendered/`)、
  Quickstart(≤3 命令)、诚实分层 Roadmap、AI-first 一节(链 AI-COLLABORATION.md)。
- 口述关:tutorials/12 的 60 秒陈述**按 EVIDENCE.md 裁成「已实现」版**,脱稿+录音自查。
- 证:陌生人按 README 10 分钟跑通;在线 demo 链接可访问。

**分支纪律(务必)**:`git switch main && git pull` → 从 main HEAD 新开 `feat/day10`;
动手前 `git log --oneline main..HEAD` 核空。

## 7. 高价值教训（面试素材 / journal 可用 / 已入记忆）

1. **红队缺陷默认当天全修,别反射性拿 INV-8 缩范围**([[redteam-fix-all-over-defer]]):
   我曾主张把 #2(全量数字守卫)推到 Day 10,Yi Xin「全部修改」否掉——全修其实很便宜。
2. **守卫自身要按它保护的边界自测**([[security-fence-self-review-blindspot]] 已强化):
   死链守卫护 INV-1 却自带 INV-1 洞,红队补上。同一盲区换形态又中一次。
3. **跨宿主红队咬到实现方漏的洞**:路径爆炸 DoS、证据守卫不全、malformed 不 fail-closed
   ——10 条里多条是 host 自查没抓到、Codex 抓到的,印证多智能体对抗设计。
4. **诚实优先**:MiniMax 首跑卡 10min 我如实记录(非隐藏);EVIDENCE.md 数字只引当前
   main 冻结件,不引历史被推翻值(Day8 推翻过 0.917→0.979)。
