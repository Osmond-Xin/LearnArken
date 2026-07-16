# Deep Research 报告审阅记录（Claude，2026-07-15）

> **AI-generated**（实现方助手对 10 份 Gemini Deep Research 报告的校对），待人审。
> 审阅深度分级：day4 全文精读（今日开工用）；day1/3/8/9/10 重点章节核查；
> day2/5/6/7 结构 + 关键论断抽查。勘误只**追加标注**，不改动 Gemini 原文
> （保留原始产物的完整性）；day4 的勘误已加注在其文件头部。

## 总体结论

10 份报告质量整体很高，方法论与本项目宪法**基本一致**（Day 3 明确"相关性
判断必须人做"、Day 8 明确"裁判与生成必须异源"）。需要处理的问题集中在
Day 4（5 处，已文内标注）和 Day 10（1 处架构适配缺口，需 Day 10 前决策）。

## 逐份结论

| 报告 | 结论 | 要点 |
| --- | --- | --- |
| day1 S1000D | ✅ 通过 | 史实核对无误（ATA 100=1956、iSpec 2200=2000、Issue 2.0=2003/4.0=2008/4.1=2012/5.0=2019）。**增量价值**：ACT/CCT/PCT 三表适用性架构、CIR 公共库引用、Inwork→Official 生命周期——均超出本项目简化模型，属 INV-7 该诚实标注的"真实世界差距"，不构成行动项。 |
| day2 XML 校验 | ✅ 通过 | 与本项目 Day 2 实现高度吻合（四层、fail-closed、sourceline 行号定位、defusedxml 防线）。引用含多处 Stack Overflow——务实来源，论断本身无误。 |
| day3 信息检索 | ✅ 通过 | **红线一致**：明确写"必须由具备领域知识的人类专家进行标注"。2 处 Grokipedia 弱引用（所支撑论断为常识级，无碍）。 |
| day4 混合检索 | ⚠ 5 处勘误 | 详见该文件头部「校对说明」。最重要的两条：① RRF 必须放 Vespa **global-phase**（该报告正确；此前 agy 模拟版把 RRF 写进 first-phase 是错的，以本报告为准）；② embo-01 参数（1536 维/4096 token）来源弱，落地前以真实 API 响应为准。**增量价值**：embo-01 具体参数、YQL 混合查询、超时优雅降级、标识符网关硬过滤（hard filter）。 |
| day5 RAG | ✅ 抽查通过 | fail-closed 定位与宪法 INV-4 一致；answer relevance 的"反向生成问题"测法是 RAGAS 标准方法，表述准确。 |
| day6 工程化 | ✅ 抽查通过 | 结构完整；1 处 SO 引用，无碍。 |
| day7 Agent | ✅ 抽查通过 | 未发现红旗。 |
| day8 对抗评估 | ✅ 通过（1 提醒） | 裁判异源原则、Cohen's Kappa 校准均正确。**提醒**：举例模型名停留在 2024 年代（GPT-4o/Claude 3.5 Sonnet/Gemini 1.5 Pro），方法论不受影响，落地时用当前模型代号。 |
| day9 可核查仓库 | ✅ 通过 | llms.txt 起源核对无误（Jeremy Howard / Answer.AI / 2024-09）。 |
| day10 部署 | ⚠ 1 处适配缺口 | 报告强烈推荐 HF Spaces（16GB 内存）并假设"**本地** BGE/FAISS 内存索引"技术栈；但本项目是 **MiniMax API + Vespa docker**——Vespa 无法跑在 Streamlit Cloud / HF Spaces 免费层。Day 10 部署方案需要专门决策（候选：demo 降级为预计算轻量索引 / 远程 Vespa / 仅录屏 + 本地跑通说明）。不是报告错误，是提示词未交代 Vespa 依赖；**列入 Day 10 SPEC 必答题**。 |

## 与本项目红线的对照（全套扫描结果）

- **golden set 标注**：day3 与红线一致；day4 建议"MiniMax-M3 反向生成 1500 条
  Query + 人工校验"——方向合规（AI 起草候选、人判定），但规模是生产级框架，
  本项目按 32 题人工判定集执行，不扩产。
- **裁判独立性**：day8 与 execution-plan 的"非实现方模型红队"原则同构。✅
- **规模假设**：day4/day10 均按十万级以上语料给建议（延迟预算、内存红线）；
  本项目为数百 chunk 玩具规模，数字按比例解读，结论方向仍有效（INV-7）。
