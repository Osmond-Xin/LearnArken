# Day 4 会话交接（Handoff）— 2026-07-16

> **AI-generated**（Claude 实现方，session 结束前交接）。目标读者：下一个
> AI session + Yi Xin。范围：Day 4a 已完成部分、收口清单、Day 4b 待办。
> 规则源：CLAUDE.md（角色边界、红队闸、当日纪要）与 docs/constitution.md。

## 0. 一句话状态

Day 4a **实现全部完成、重型红队已跑、五项裁决已执行**（120 测试全绿，
分支 `feat/day4` @ `2ea1371`，13 个 commit，**未合并未打 tag**）；剩收口
动作（多数需要 Yi Xin 决策）+ Day 4b。**注意：Day 3 也还没合并**——
`feat/day4` 叠在 `feat/day3` 上，收口要先走 Day 3 的 PR。

## 1. Day 4a 交付了什么（均已提交）

| 交付物 | 位置 | 要点 |
| --- | --- | --- |
| LangChain = 系统默认技术栈 | `embedding/providers.py`、`retrieval/{bm25,dense,hybrid}.py`、`chunking/documents.py` | 原则「框架管管道原语，领域逻辑自留」；Day 1–2 审计为无等价物不改；`langchain_classic` 供 EnsembleRetriever/CrossEncoderReranker，`langchain-community`（已日落，风险已登记）供 BM25Retriever |
| **Qwen3-Embedding-8B = 唯一 dense provider** | `embedding/providers.py` | 三方 bake-off 定的（0.99 vs BGE-M3 0.92 vs MiniMax 0.50）；**MiniMax 已按裁决整体移除**（连 config.py/.env 一起），历史代码在 commit `b414fa4` |
| MiniMax 长度偏置发现 | `docs/notes/day4-embedding-length-bias.md` + `tools/probe_length_bias.py`（自包含可复跑） | 同句重复语义不变余弦 0.76→0.58；无关短块击败正确长块；LangChain 协议等价 + BGE 对照双重排除配置嫌疑 |
| Vespa 稠密存储 | `vespa/app/`（schema 4096 维、prenormalized-angular）、`vespa/store.py` | 只做 nearestNeighbor + 属性过滤（Q3/Q4 可迁移性裁决）；喂数幂等（doc id = chunk_id）；**corpus manifest 验证**（`.vespa-manifest.json` + visit API 集合比对，fail-closed） |
| 四模式检索 + 消融 | CLI：`index` / `search --mode bm25\|dense\|hybrid\|hybrid-rerank` / `eval ablation` | RRF=EnsembleRetriever(id_key=chunk_id)、rerank=bge-reranker-v2-m3（Python 侧）；融合臂带 `GuardedBM25Retriever` 拒答护栏（红队 #6 修复） |
| 语义分块（第三策略） | `chunking/semantic.py` | 邻句距离百分位切分；分块表：structure 0.93 > recursive 0.85 > semantic 0.81 → 消融固定用 structure |
| Golden set 82 题 | `eval/golden/day4.jsonl` | **全部人工复核完毕**（Yi Xin 2026-07-16，复核时改过 anchor）；10 类别 |
| 基准表（防手编） | `eval/results/day4-ablation.json` + `tools/gen_benchmark_tables.py` → README | 生成器内置 Recall 单调性拒绝 + answerable n=67 标注；**README 表格禁止手编**（红队 P0 #1 的教训） |
| 红队评审 | `docs/reviews/day4.md` | Part 1：Codex 跨主机 17 条（4 P0/7 P1）；Part 2：五项裁决已转录并执行 |
| 决策链 | `docs/discussions/day4.md` D1–D17 | 当天全部决策留痕 |

**当前消融表**（answerable n=67，结论稳定）：bm25 0.83/0.88、dense
**0.99/1.00**、hybrid 0.93/1.00、hybrid-rerank 0.99/0.99；zero-hit 仅纯
bm25 0.40——**含 dense 的模式构造上不可拒答**，真拒答是 Day 5 答案层职责。

## 2. Day 4a 收口清单（新 session 按此执行）

1. **红队遗留 8 条待 Yi Xin 裁决**（docs/reviews/day4.md Part 2 末尾）：
   **#5 跨包检索范围（Day 5 引用接地前置，建议优先）**、#8 Vespa 端口绑
   127.0.0.1、#9 YQL 参数化、#10 下半 HF 模型 pin revision（INV-5）、
   #12 集成测试套件、#13 消融重复搜索、#14 适用性下推、#16/#17 小项。
   裁决后按裁决修复或入 backlog。
2. **Day 4b 开门判据宣读 + ADR**（需 Yi Xin 决定）：复核后数字下
   paraphrase 缺口被 dense 关死（1.00）、标识符类 rerank 1.00——按
   「用数字开门」，SPLADE 和 ColBERT 的门**都没开**。维持关门（写 ADR）
   还是 Yi Xin 以学习价值为由 override（Day 4b 做，D5/D13 已备好路线：
   BGE-M3 一模型供 sparse+ColBERT 三表征；注意 D7 记录的引擎耦合矛盾）。
3. **Day 4 复评点**（execution-plan 🔁，需 Yi Xin 决定）：最小 RDF/SPARQL
   图查询拉回切片与否 → ADR（docs/adr/ 目录还不存在）。Neo4j 容器已跑、
   空库；chunk 已带图谱钩子（dmRefs/ICN）。
4. **计划文件修订**（Q7 裁决过但未落笔）：execution-plan.md 加 4a/4b 拆分；
   README Roadmap 的 SPLADE/ColBERT 从 Planned 改「Day 4b, evidence-gated」。
5. **SPEC 验收清单打勾**（docs/specs/day4.md Acceptance Criteria 逐条核对）。
6. **合并链**：先 Day 3（`feat/day3`→main，PR+squash+tag `v0.3.0`），再
   rebase `feat/day4` → PR → squash → tag `v0.4.0`（4a+4b 共用一个 tag，
   Q7 裁决）。PR 描述 = SPEC 链接 + 验证方式。
7. **人写产出**（Yi Xin，AI 不碰）：docs/journal/day4.md；顺带 day3 的
   journal 状态也确认一下。
8. 提醒：执行计划注明 **Day 4 完成 = Projects 简历行与 AI 赛道解锁**（私档）。

## 3. Day 4b（若开门/override）

范围（D5）：SPLADE + ColBERT，判据驱动。技术路线（D13/D14 已铺）：
BGE-M3 已下载，一个模型产 dense+sparse(词权重)+ColBERT 多向量；Vespa 是唯一
全支持三表征的引擎（官方 pyvespa 笔记本「mother of all embedding models」）。
**先解决 D7 记录的矛盾**：ColBERT「原生」= 引擎内 embedder+MaxSim rank 表达
式，正是 Q3 否掉的引擎耦合——要么 Day 4b 接受耦合，要么 Python 侧 MaxSim
（玩具规模可行）并重述 D2 选型理由。无独立 tag，计入 v0.4.0，受 INV-8
两日历日上限约束（Day 4 已用 2026-07-15/16 两天——**INV-8 已到顶，注意**）。

## 4. 环境事实（新 session 无需重建）

- **Vespa**：容器 `learnarken-vespa` 运行中，应用包已部署（schema 4096 维），
  43 个 structure chunks 已喂（package-a+c，Qwen3 向量），manifest 在
  `.vespa-manifest.json`（git-ignored）。8080 查询 / 19071 config。
  schema 改维度需 `validation-overrides.xml`（现有条目 2026-07-23 过期）。
- **Neo4j**：`learnarken-neo4j` 运行中，空库，neo4j/learnarken。
- **本地模型**（~/.cache/huggingface，已缓存）：Qwen3-Embedding-8B（fp16 on
  MPS）、BAAI/bge-m3、BAAI/bge-reranker-v2-m3。机器 M5 Max/64GB。
- **不再需要 `.env`**——MiniMax 已移除；历史证据脚本自行读 FollowTheBig/.env。
- 验证命令：`make test`（120 全绿）、`make lint`、
  `uv run learnarken eval ablation --json > eval/results/day4-ablation.json`、
  `uv run python tools/gen_benchmark_tables.py`（表格唯一来源）。

## 5. 高价值教训（面试素材，journal 可用）

1. 供应商缺陷的根因三角验证：协议等价（LangChain 请求逐位一致）+ 对照模型
   + 文献类比 → "是模型不是配置"。
2. 手编基准表出了数学上不可能的行（R@5>R@10）→ 表格必须由产物生成、
   生成器拒绝非法行。
3. 融合会静默吃掉单臂的安全性质（拒答护栏），且"修好了护栏 zero-hit 仍是
   0"——因为 dense 构造上不拒答，融合继承之。安全性质要在系统层重新证明。
4. 教科书失败模式（dense 输标识符）在 8B 模型 + 玩具语料下**反转**——
   尺度与模型依赖，别照抄结论。
