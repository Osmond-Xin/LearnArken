# 会话交接（Handoff）— 项目收口后「全项目扫描 + 梳理」session

> **AI-generated**（Claude 实现方,v1.3.0 收口后交接）。目标读者:下一个 AI session
> + Yi Xin。**本交接与之前的每日交接不同**——十日切片已全部收口,下个 session 不是
> 「启动 Day 14 实现」,而是**对整个项目做一次完整扫描、补齐未完成的部分(重点:架构
> 文档)、做总结与梳理**。规则源:CLAUDE.md 与 docs/constitution.md。**权威细节以各
> 文档/代码为准,勿仅凭本文摘要行动。**

## 0. 一句话状态

**10 日切片全部收口,v0.1.0 → `v1.3.0` 已 push origin,GitHub CI 绿。** `main` HEAD
= `acd7a88`(Day 13 的 ruff format CI 修复,前一个是 `df1ba46` = Day 13 主实现,tag
`v1.3.0` 打在它上)。`main` 与 `origin/main` 同步,工作树干净,**430 passed / 9 skipped,
ruff check + ruff format --check 全绿**。所有分支已合入 main(一天一分支,已删)。

## 1. 本 session 的三件事(Yi Xin 指定)

1. **全项目完整扫描**——通读 `src/`(66 个 .py)、`docs/`、`tests/`、`tools/`、
   `eval/`,建立当前**真实**状态的全局图,不靠记忆。
2. **补齐未完成的部分**——**最大的一块是架构文档**(见 §2,已陈旧 3 天/3 个切片)。
3. **总结与梳理**——面向求职/面试的项目总结、目录梳理、可能的一致性清理。

> 注意:本 session **不受每日七步循环约束**(没有新 SPEC 决策层要写、没有新红队闸要
> 跑,除非产生了新代码)。但**红队闸规则仍然生效**:如果扫描中你**改动了代码**(不只
> 是文档),则改完绿了、提交前**必须**跑跨宿主 `coding-adversarial-review`。纯文档整理
> 不触发红队闸。

## 2. ⚠️ 最大的待补:架构文档陈旧 3 个切片(Day 11/12/13 未纳入)

`docs/architecture/`(README + 01–05)**快照日期是 2026-07-18,Day 1–10 / `v1.0.0`**。
之后的三天**完全没进架构文档**。已核实缺失:

- **Day 11(KG-RAG,`v1.1.0`)**:`retrieval/entity_link.py`、`retrieval/graph_expand.py`、
  `graph/`(Neo4j)进检索路径(第三路 RRF)——`01-file-inventory` / `02-system-architecture`
  未纳入。
- **Day 12(多模态,`v1.2.0`)**:`multimodal/{vlm,ingest,figures,second_look}.py`、
  `answer/figure_relook.py`、describe-then-index 管线、G15 视觉拒答——全缺。
- **Day 13(性能与推理策略,`v1.3.0`)**:`perf/{shard,orchestrate}.py`、
  `repair/tot.py`、`validation/parallel.py`(engine 拆 `_process_file`/`_merge_file_results`)——全缺。

**核实命令**(下个 session 先跑,别信本文摘要):
```bash
for m in perf/shard perf/orchestrate repair/tot validation/parallel \
         multimodal/vlm multimodal/ingest second_look entity_link graph_expand; do
  grep -ql "$m" docs/architecture/01-file-inventory.md && echo "IN  $m" || echo "MISS $m"
done
```
**建议做法**:更新 `01-file-inventory`(补 Day 11/12/13 全部新文件)、`02-system-architecture`
(检索路径加图谱第三路 + 多模态入库/问答子系统 + perf 的 mp/asyncio 分工)、`04-tech-selection`
(补 numba/Rust/free-threading 证据门 = ADR-0003、ToT/BoN 选型、Qwen3 本地嵌入),并把
README 快照日期推进到 `v1.3.0`/2026-07-21。**标注 AI-drafted 待人审**(既有约定)。
架构文档的 mermaid 在 `docs/diagrams/*.mmd`,一并核对是否需更新。

## 3. 其他待办尾巴(可选,按价值排)

- **`README.zh-CN.md` 自 Day 10 停更**:标题还写「进度(Day 1–10)」、Day 10 都还是 ⬜,
  Day 11/12/13 完全没有。英文 README 是**唯一维护**的(已含 Day 13 节 + 进度表 + Roadmap)。
  要么补齐中文版、要么在中文版头部明确标「已归档,以英文 README 为准」——**这是决策,问 Yi Xin**。
- **幻觉边界分级配置表**(Yi Xin 2026-07-20 提,`docs/notes/day12-hallucination-boundary.md`):
  自由文本门当前一刀切、偶发误拒;方向=按后果分级(颜色可容忍/扭矩零件号硬拒)的 config。
  独立议题,可专议。
- **Day 8 遗留**(README Roadmap 有列):数字/单位感知匹配(`125 Nm` 不应满足 `25 Nm`)、
  裁判熔断(硬上限非仅超时)、index content-hash/epoch。
- **ToT reward-hack veto 是行级删除比例的粗信号**(Day 13 红队 #5 诚实标注):按后果/
  按删的是引用还是业务数据来分级是 Roadmap;`repair/tot.py` `REWARD_HACK_DELETE_FRACTION=0.5`
  是 toy 常量。
- **多模态二次看图「答案从再读构造」**、**PPR/图算法排序**、**LLM/NER 实体链接兜底**——
  各自 Roadmap(day11/12 收尾时记的)。
- **本地 lint 门要和 CI 对齐**(本 session 踩坑):CI 跑 `ruff check` **且** `ruff format
  --check src tests`;push 前本地两条都要跑(见记忆 `local-green-not-ci-green` 新变种)。

## 4. 全项目地图(13 天产物)

- **代码**:`src/learnarken/` 66 个 .py。子系统:`validation/`(四层校验 L0–L3 + mp 分片)、
  `chunking/`、`embedding/`(Qwen3-8B 本地)、`retrieval/`(BM25=Tantivy / dense / hybrid /
  graph 第三路 / RRF / rerank)、`vespa/` + `graph/`(存储)、`answer/`(引用/拒答/trace/
  SSE/figure_relook)、`repair/`(Day7 ReAct agent + Day13 ToT + 沙箱)、`multimodal/`(Day12)、
  `perf/`(Day13 mp+asyncio)、`adversarial/`(Day8)、`api/`(FastAPI+demo_guard)、`llm/`(MiniMax)。
- **每一天的决策链**(逐日齐全):`docs/specs/dayN.md`(决策层人写/转录)、`discussions/dayN.md`、
  `reviews/dayN.md`(红队 Part1 + 裁决 Part2)、`journal/dayN.md`(人写)、`research/dayN-unknowns.md`
  (扫)、`gemini-deepresearch/`(研)。
- **横切文档**:`constitution.md`(INV-1–8 最高权威)、`execution-plan.md`、`project-design.md`、
  `architecture/`(⚠️陈旧,见 §2)、`EVIDENCE.md`(证据链/复跑命令)、`AI-COLLABORATION.md`、
  `adr/`(0001 Day4b 门 / 0002 图查询切片 / 0003 Day13 Rust·FT 门)、`tutorials/`(00–16,
  面试导向,老技术类比)、`llms.txt`(机器可读,Day9)。
- **评估产物**:`eval/results/*.json` + `eval/golden/`(固定 seed,INV-5;`tools/gen_benchmark_tables.py
  --check` 保证 README 表与产物一致)。
- **样本**:`samples/package-a`(合法)、`package-b`(已知违规,Day8/13 用)、`package-c`;
  `samples/s1000d/`(真实结构参考,非提交、只读、禁抄内容,INV-1)。

## 5. 环境事实(新 session 无需重建)

- **Vespa** `learnarken-vespa`(`127.0.0.1:8080/19071`)、**Neo4j** `learnarken-neo4j`
  (`7474/7687`):**两容器需手动 `docker start`**,不随 session 自动起。重建索引前先
  `vespa.clear()`(index 是 upsert,chunk_id 变了会留 stale)。
- **VLM/LLM = MiniMax 代理**(`.env` `MINIMAX_*` 四键):有 vision 但不稳定,订阅制、
  `429`=终止信号;不用新 key(记忆 `minimax-vision-channel`)。**CI 跑干净环境无 .env**——
  新测试必须 hermetic(push 前 `mv .env .env.bak` 复现 CI 跑一遍)。
- **裁判 CLI**:`codex`(红队闸走 `codex exec --sandbox read-only`);`agy` 在;`gemini` CLI 已死。
- **依赖**:Python 3.12 基线(dev venv 是 3.13,`uv run --locked`);Day13 新增无(numba/Rust
  都没上,证据门未开)。`pillow` 是 Day12 加的。

## 6. 规则提醒(consolidation 版)

- **AI 永不碰**:`docs/journal/`、`reviews/` 的裁决半(Part2,除非 Yi Xin 明确授权转录 + 留痕,
  如 Day13 的做法)。
- **架构文档 = elaboration 层**,AI 可起草,标 `AI-drafted 待人审`。
- **改了代码就跑红队闸**(§1);纯文档整理不触发。
- **诚实纪律**:数字带复跑命令(INV-5)、不涨照报、toy 规模声明(INV-7);梳理/总结时
  别把「诚实的平/无提升结果」美化成成功(Day 4b/11/13 的诚实结论是资产,不是要藏的东西)。
- **对话默认中文**汇报,仓库产出(spec/代码/评审/架构)按惯例英文。

## 7. 建议执行顺序

1. 先跑 §2 的核实命令 + `git log --oneline -15` + `make test` + `make lint`,确认起点。
2. 全项目扫描,产出一份「现状 vs 文档」差异清单(架构缺口是最大一项)。
3. 补架构文档(01/02/04 + README 快照日期 + diagrams),AI-drafted 待人审。
4. 决策项抛给 Yi Xin:zh-CN README 补齐还是归档?总结文档要不要单开(面试用)?
5. 若过程中改了代码 → 红队闸 → 修 → 绿 → 提交(小 commit,Co-Authored-By)。
6. 纯文档:直接提交(conventional,`docs:` 前缀)。**push 只在 Yi Xin 要求时。**
