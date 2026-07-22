# Day 11–13 规划讨论：JD 对位扩展切片

> **AI-distilled**（Claude，2026-07-19，待人审）。本次讨论发生在 v1.0.0 收口后，
> 内容为求职投递复盘引出的范围决策。目标岗位分析在私档（不入仓库），此处只记
> 与仓库相关的工程决策。

## 问题

Day 1–10 切片对照目标岗位 JD 复盘，标题级关键词还有两个缺口：

1. **Knowledge-Graph RAG**：图谱做到了影响查询（接口①，Day 9）和上下文注入
   （接口③，Day 5），但从未进入检索路径——严格说现状是"KG-assisted"，
   不是 "KG-RAG"；
2. **Multi-Modal**：全切片纯文本，ICN 插图内容从未入库。

同日追加（同一复盘的第二轮讨论）：JD 技能行要求 **Python mastery
（asyncio / multiprocessing / Cython/numba；Rust/C++ 为 plus）**。Yi Xin 的
现状：早年经历过共享状态多线程的维护成本，此后一贯用架构规避（队列、无状态、
幂等）——理念正确（share-nothing），缺的是术语对齐、工具肌肉和可展示的基准
数字。

同日第三轮：JD 行 **multi-agent systems (ReAct, ToT, GoT, MCTS) +
world-model simulation + counterfactual reasoning + adversarial
self-critique** 如何应对。盘点：ReAct（Day 7 修复 agent）、对抗质检
（Day 8 + 全程红队流程）、反事实归因（Day 8 缺陷消除前后对比实验）、
world-model 工程雏形（dry-run 沙箱）均已有实现证据；缺口只在搜索类
（ToT/GoT/MCTS）。

是否扩展切片补齐？怎么补才不破坏既有纪律？

## 选项

| 选项 | 内容 | 弃/采 |
| --- | --- | --- |
| A. 不补，README Roadmap 标 Planned | 零成本，但 JD 标题词覆盖靠嘴说 | 弃：标题级关键词值得真做 |
| B. 全量补（RDF/SPARQL 全图 + ColPali 视觉检索） | 覆盖最全 | 弃：违反切片纪律，工期不可控 |
| C. 各补一个 1–2 日最小切片（Day 11/12） | KG-RAG 复用 Day 9 引用图做第三路融合信号；多模态走 describe-then-index 复用全部现有设施 | **采** |

## 决策

1. **Day 11 = 图谱增强检索**（`v1.1.0`）：实体链接（确定性优先）→ 1–2 跳邻域
   扩展 → RRF 第三路；消融表加 hybrid+graph 一行；多跳 golden 题新旧分开报分；
   **不引入 RDF/SPARQL**，全量图谱仍在 Planned。
2. **Day 12 = 多模态入库与问答**（`v1.2.0`）：合成 ICN 插图（INV-1 红线不变）；
   VLM 受控结构化描述（schema 约束 + XML hotspot 集合互验 + checksum 绑定）进
   现有索引；图引用可审计；超描述范围 fail-closed 拒答。
3. **Day 13 = 性能工程**（`v1.3.0`）：四层各挣一行基准——asyncio
   （Semaphore 限流批量调用，串行 vs 并发 wall-clock）、multiprocessing
   （分片校验扩展曲线 1/2/4/8 worker + 拐点分析，正好落实 INV-2）、
   profile→numba（py-spy 定位真热点，三列对比，收益小如实报小）、
   Rust/PyO3 仿 Day 4b **证据开门**（profile 证明 Python 侧是瓶颈才立项，
   不开门写留痕结论）。搜索类 JD 行**不专开一天**：并入一个半日
   **玩具 ToT 实验**（修复 agent 单候选 vs 3 候选 + 沙箱验证器打分，
   报修复成功率 × token 成本两列），其余（GoT/MCTS/world model 全量）保持
   "概念掌握 + 适用边界判断"的第二档口径。
4. 七步循环、滑点规则、"SPEC 决策层人写"照旧——本次只写计划占位
   （execution-plan.md 阶段三）与配套教程（tutorials/14、15、16）、深研提示词
   （deep-research-prompts.md Day 11/12/13），specs/day11–13.md 待人写。

## 理由

- 两个缺口都选**复用最大化**路线：Day 11 复用引用图与 RRF 框架，Day 12 复用
  文本检索、引用、拒答、评估全套——每个 1–2 日可收口，符合滑点纪律。
- 收益定位诚实：KG-RAG 消融"涨平都如实报"（假设待验证，延续 Day 8 的评估
  纪律）；多模态标注玩具规模（INV-7）。
- 选型上放弃 GraphRAG（LLM 抽图幻觉风险 + 全局摘要问题不在高价值查询里）与
  ColPali 路线（页级引用粒度与"引用精确到 chunk"红线冲突），理由写入教程
  14/15 的版图节，面试可复述。
- Day 13 的定位是**把已有的正确直觉换成现代术语并配上证据**，不是从零学并发：
  "规避共享可变状态"直接对应 asyncio 单线程模型与 multiprocessing 进程隔离，
  面试叙事从"我避免并发"改写为"我避免共享可变状态"；Rust 不硬造玩具项目，
  以"知情消费者"（本栈经 pydantic-core/tokenizers 消费 Rust;Tantivy/Qdrant 是行业例子、非本项目所用）+ 证据开门的姿态呈现，与 Roadmap
  诚实分层一致。
- ToT 实验并入而非专开的理由：全部设施现成（候选生成 = 现有 agent 换采样，
  验证器 = Day 7 沙箱复验，评估集 = package-b 违规清单），半日可收口；
  且"多候选 + 确定性验证器"是 ToT 的最小可用形态，成本两列如实报——
  **"何时不值得上搜索"的实测答案本身就是面试资产**（延续 Day 4b/numba
  同款"证据说话、不涨照报"纪律）；候选生成并发化正好用上本日 asyncio，
  两个主题自然衔接。生产共识（能 workflow 别 agent、能线性别搜索）作为
  第二档口径的理论支撑，写入教程 09 复习范围。
