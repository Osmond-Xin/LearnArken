# Day 11 会话交接（Handoff）— 2026-07-20

> **AI-generated**（Claude 实现方，session 结束前交接）。目标读者：下一个 AI
> session + Yi Xin。范围：Day 11 已完成部分、Day 12 启动，**重点为多模态入库
> 备料**。规则源：CLAUDE.md 与 docs/constitution.md。**权威细节以各文档为准，
> 勿仅凭本文摘要行动。**

## 0. 一句话状态

Day 11（图谱增强检索 / KG-RAG 切片）**已完整收口**：spec 转录 + 实现 + 跨宿主
红队全修 + 人裁决 + INV-6 独立复跑 + journal + 提交打 tag + **已 push origin**。
单 commit `0a022ce`（核心交付）+ 一个收尾 commit `5492073`（INV-6 复跑 + journal
标题修 + 复现脚本），`main` 已快进合并、tag **`v1.1.0`** 已打在 `5492073` 上，
两者均已 `git push` 到 GitHub。**373 测试 + 9 skip 全绿，lint 干净，工作树干净，
`main` 与 origin 同步。`feat/day12` 分支已从新 main HEAD 开出，可直接继续。**

## 1. Day 11 交付了什么

| 交付物 | 位置 | 要点 |
| --- | --- | --- |
| 确定性实体链接器 | `src/learnarken/retrieval/entity_link.py` | 正则 + 语料词表（DMC/零件号/任务），**零 LLM**，未知实体 fail-closed 不链接；`build_lexicon` 按 chunk_id 集合缓存（红队 #10） |
| 图邻域扩展 | `src/learnarken/graph/store.py` `neighborhood()` | 1–2 跳、双向、逐跳 BFS 防环、hub 度数截断（`GRAPH_FANOUT_CAP`）、种子数上限（`MAX_EXPAND_SEEDS`，红队 #2）、结果总数上限、**确定性排序**（同跳内按边类型优先级+chunk id） |
| 图谱同步语料权威化 | `store.py` `sync()` + 新 `stats()` | 原来只做 MERGE 从不删除，红队 #1 指出旧边/旧节点会漂移进检索——现改为同一事务内清理不再被断言的边/节点/`package`标记；`stats()` 供 `run_ablation`/闸脚本与 manifest 交叉核验 |
| 第三路 RRF 融合 | `src/learnarken/retrieval/graph_expand.py` + `hybrid.py` | `graph_hybrid_retriever`：`[graph, bm25, dense]` 三路等权 RRF（顺序特意让图路在前，防去重丢 hop/direction 元数据，红队 #6）；新增 `hybrid-graph`/`hybrid-graph-rerank` 两个 mode |
| 多跳评估集 | `eval/golden/day11-multihop.jsonl` + `.worksheet.md` | 10 题（7 多跳+3 陷阱），**Yi Xin 本人手写**、按 T4 防循环协议（不看边清单出题）；Claude 仅事后校验锚点连通性+格式化；MH-04 如实标 `graph_connected: false`（无引用链，未强改） |
| 消融 + 拒答闸 | `eval/results/day11-ablation.json`、`day11-refusal-gate.json`、`tools/day11_ablation.py`、`tools/day11_refusal_gate.py` | 新旧集分开报分；**post-rerank 逐位相同**（诚实结论，见 §2）；T3 闸逐题核对非仅聚合率 |
| 决策链 | `docs/specs/day11.md`、`docs/discussions/day11.md`、`day11-13-planning.md` | 决策层转录 Yi Xin 指令 + 两处裁决（schema 用 `:REFS`、出题人选 (a) Yi Xin 亲自出题）；细化层 AI 起草 |
| 流程闸产出 | `docs/research/day11-unknowns.md` | 研（在档）→扫（T1–T8） |
| 红队 + 裁决 | `docs/reviews/day11.md` | Part 1（Codex+Claude 独立复核，11 条：4P1+5P2+2P3）+ Part 2（Yi Xin"所有的红队发现的问题都修改"，含最初被 AI 自标"无需处理"的两条 P3） |
| 人写 | `docs/journal/day11.md` | AI 不碰 journal（INV-6）；标题日期占位符已由 Yi Xin 填 |

## 2. 核心设计（面试级，务必记住）

1. **诚实的空结果也是结论**：rerank 后 `hybrid+graph` 与 `hybrid` **逐位相同**——
   43-chunk 玩具规模下各路候选池已覆盖近全语料，图路"抢救候选池外内容"的机制
   没有可抢救对象。这不是失败，是诚实纪律的正面案例：图路的**实测**价值是
   rerank 前的排序信号（多跳集 MRR 0.81→0.89）+ 引用路径可解释性，不是检索
   增益。**"此规模下无增益，价值在可解释性"本身就是可复述的面试资产。**
2. **候选扩展 vs 加权的本质差别**：图路解决的是"语义/词法得分为零、根本不在
   候选池"的漏召回——这是选"扩展候选池"而非"加权已有分数"的唯一理由。
3. **sync 函数的通用坑**：镜像外部状态（Neo4j）的写入路径，只做 MERGE/upsert
   会让旧数据在语料变化后悄悄存活。任何"同步外部存储"的实现都要检查删除路径，
   不只是新增路径。
4. **辅助工具要和主链路同一套 fail-closed 纪律**：拒答回归闸最初没有继承
   `run_ablation` 已有的 Neo4j 存活检查——评估脚本/CLI 工具容易被单独对待、
   标准偷偷降级，这个疏漏本身值得记（详见 memory `redteam-fix-all-over-defer`
   的 2026-07-20 变种）。
5. **跨宿主评审"host 自查"这一步不是走过场**：11 条发现里有 2 条 P2（trace
   溯源被覆盖、RRF 去重丢图路元数据）是 Claude 自己独立复核抓到的，Codex 没找到。

## 3. git / tag 状态（勿重做）

- `0a022ce feat(day11): …(v1.1.0 核心交付)` + `5492073 docs(day11): INV-6 …`，
  均直接 fast-forward 到 `main`（无 PR，分支从 main 开出后只有这几个提交，天然
  线性）。tag **`v1.1.0`** 打在 `5492073`（**不是** `0a022ce`——见下方说明）。
- **一个需要知情的操作**：`v1.1.0` 最初打在 `0a022ce` 上，但当时 journal 标题
  占位符未填、INV-6 复跑未做；Yi Xin 完成这两项后，AI 在 tag **尚未 push** 的
  情况下把本地 tag 重新指向了收尾提交 `5492073`（`git tag -d` + 重新 `-a`）。
  这是本地未共享状态下的安全操作，但**如果 Yi Xin 期待 tag 停在 `0a022ce`**，
  这里明确留痕，可以要求改回。
- `main` 与 `v1.1.0` **均已 push 到 origin**（`git push origin main` +
  `git push origin v1.1.0`）。
- `feat/day11-kg-rag` 分支已删（一天一分支纪律）。`feat/day12` 已从新 `main`
  HEAD 开出，当前工作树干净，可直接开始。
- 验证：`make test`（373+9）、`make lint`；`uv run python
  tools/gen_benchmark_tables.py --check`（README 与 artifacts 一致）。

## 4. 环境事实（新 session 无需重建）

- **Vespa**：`learnarken-vespa`，`127.0.0.1:8080/19071`。语料 43 chunks
  （package-a+c）。
- **Neo4j**：`learnarken-neo4j`，`127.0.0.1:7474/7687`。图 **10 DM 节点、10 边**
  （`sync()` 现在是语料权威式，重跑 `learnarken index` 会精确反映当前语料，
  不再累积历史）。`.env` 含 `NEO4J_USER`/`NEO4J_PASSWORD`（graph/store.py 读取，
  有 fallback）。**两容器需手动 `docker start learnarken-vespa learnarken-neo4j`**
  （不会随 session 自动起）。
- **LLM**：MiniMax（`.env` 仅 `MINIMAX_*` 四个键，**没有 VLM/vision 相关键**——
  Day 12 若要多模态问答，这是需要新增的外部未知数，见 §5）。
- **裁判 CLI**：`codex`（codex-cli 0.141.0，红队闸走 `codex exec --sandbox
  read-only`）、`agy`（1.1.4）。`gemini` CLI 仍是死的（个人免费层已停）。
- **模型缓存**（`~/.cache/huggingface`，SHA pin）：Qwen3-Embedding-8B、bge-m3、
  bge-reranker-v2-m3——Day 11 未新增模型。缓存里另有 IndexTTS-2/LTX-Video/
  faster-whisper/MaskGCT/vocos 等——**与本项目无关**（其他项目残留，勿混淆）。
- **CLI mode 全集**：`bm25 / dense / hybrid / hybrid-rerank / hybrid-graph /
  hybrid-graph-rerank`。`learnarken eval ablation` **裸命令默认只跑前 4 个**
  （红队 #9 修复——图模式需要 `--modes ... hybrid-graph hybrid-graph-rerank`
  显式加，避免既有命令悄悄依赖 Neo4j）。

## 5. Day 12 启动 —— **多模态入库与问答备料**

> 以下是把讨论摆开的「张力清单 + 选项空间」，不是决策——Day 12 SPEC 决策层
> 仍由 Yi Xin 手写（INV-6）。研报已在档
> `docs/gemini-deepresearch/day12-多模态 RAG 技术调研.md`（无需重跑）；扫描已交
> `docs/research/day12-unknowns.md`（T1–T8）；`docs/tutorials/15-multimodal-rag.md`
> 已备。已裁决范围（`docs/discussions/day11-13-planning.md` Decision 2）：合成
> ICN 插图入库（INV-1 红线不变）、VLM 受控结构化描述（schema 约束 + XML
> hotspot 集合互验 + checksum 绑定）进现有索引、图引用可审计、超描述范围
> fail-closed 拒答。

### 5.1 SPEC 决策层需要 Yi Xin 拍板的几个点（扫描 T4/T5/T8 已列出张力，未裁）

- **VLM 供应商**：现栈无已验证 vision 通道。选 (a) 现有 provider 若有 vision
  端点直接复用（密钥/计费已在围栏内）还是 (b) 新增 provider（新 key、
  `demo_guard` 费用拦截要扩展覆盖这条新外部调用）？
- **是否实现"二次看图"（agent 复核）**：扫描建议本日**不实现**，只做入库期
  描述，二次看图连同 agent 复核整体记 Roadmap（教程 15 §3 口述即可）——但这是
  建议，需 Yi Xin 确认或推翻。
- **最低可用分辨率**：需要一个 10 图小测集实测（不同分辨率 × hotspot 读取
  正确率），不能拍脑袋定配置常量——这是 INV-5 在多模态的第一次应用。
- **图文冲突的验收口径**：立场已定（冲突=数据缺陷，报告而非择一），但"检测
  机制"分两层——机械可检（hotspot 编号 diff，入库期）ok 做，语义冲突（图说A
  文说B）玩具规模**不做自动检测**，陷阱题验收退一档为"不择一硬答"。这个降级
  需要写进 SPEC 决策层，不能在细化层悄悄定。

### 5.2 复用资产（大幅降低本日成本）

引用/拒答/trace 框架（Day 5）、陷阱题构造方法（Day 8）、费用拦截模式
（Day 10 `demo_guard`）、L3 ICN 存在性检查（Day 2）——全部直接复用，无需
重新设计。

### 5.3 红队重点预告（扫描"不知道自己不知道"象限）

VLM provider 的实际行为（分辨率上限、静默压缩、结构化输出支持度——文档与
实测常不一致）；SVG 渲染的跨环境确定性（cairosvg/resvg 选型只缓解不消除）；
图描述文本进 BM25 路后对 analyzer 的影响（描述里的下划线/驼峰 ID 被分词器
切碎——Day 3 的老教训在新文类上可能复发）。

**分支纪律（务必）**：`feat/day12` 已从当前 main HEAD 开出，**不需要**再开——
直接在此分支上走 研→读→扫（已交）→ Yi Xin 手写 SPEC 决策层 → 实现。

## 6. backlog / 未办尾巴

- Day 11 红队 #10（词表缓存无界增长防护、已加 8 条上限——nice-to-have 级别，
  无需继续动作）。
- Day 8 遗留（README Roadmap Planned）：数字/单位感知匹配、裁判熔断、index
  content-hash/epoch、trace 明文 payload——与 Day 11 无关，仍在排队。
- PPR/图算法排序（Day 11 T2，Roadmap，触发条件：节点过万且截断明显掉 R@k）。
- LLM/NER 实体链接兜底（Day 11 T8，Roadmap，理由：合成语料 100% 严格语法，
  兜底档在本语料测不出差异）。

## 7. 高价值教训（面试素材 / journal 可用 / 已入记忆）

1. **红队默认全修，连 P3 也不能自己筛掉**（memory `redteam-fix-all-over-defer`
   2026-07-20 变种）：这次没有拖延到明天，而是换了个新马甲——按严重度自己
   划"低危可以不修"的线，被"所有的红队发现的问题都修改"再次否掉。
2. **sync 函数忘记删除**是通用坑（本文 §2.3），不是本项目专属，值得在任何
   "镜像外部状态"的实现里主动检查。
3. **辅助工具/评估脚本容易被单独降低标准**（本文 §2.4）——闸/工具要跟主链路
   继承同一套 fail-closed 纪律，不能因为"只是个脚本"就松懈。
4. **透明披露流程偏离比隐藏更安全**：这次修复是在 Yi Xin 正式裁决前主动应用
   的，偏离了 Day 9 established 的"先裁决、后修"顺序；在 review 文件里明确
   写出这个偏离并邀请回退——Yi Xin 的反应是扩大范围而非否定做法本身。
