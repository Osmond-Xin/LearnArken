# 架构文档（Architecture）

> **AI-drafted**（Claude，实现方助手），基于 Day 1–13 已合并代码、docs/specs、
> docs/discussions、docs/reviews 与 docs/local-services.md 蒸馏，**待 Yi Xin 审阅**。
> 快照日期：2026-07-21（Day 1–13 全部合并，打标至 `v1.3.0`，十三日切片收口）。
> 本文件夹只记录"已经是什么、为什么这么选"，不做新决策；所有决策出处均给出链接。
>
> **v1.3.0 补章（2026-07-21）**：本轮把 Day 11（KG-RAG 图谱检索第三路）、Day 12
> （多模态入库/问答）、Day 13（性能与推理策略实验）纳入 01/02/04；03/05 因 Day 11–13
> 未改动配置/API/demo 面，只在头部加 `v1.3.0` 一致性说明（内容仍准确）。补章内容
> 同样标 `AI-drafted 待人审`。

## 这个文件夹是干什么的

1. **解释与演示**：向读者（自己、面试官、招聘方的 AI agent）解释每个文件/模块的
   设计思路与架构细节；
2. **评估基线**：评估当前架构的适应性（能不能接住 Day 4–10 的增量）与稳健程度
   （哪些是工程化的、哪些是玩具层，诚实分层 INV-7）;
3. **变更基准**:后续任何架构变更（换向量库、加图查询、改分块策略）以本文件夹的
   快照为对照基础，变更时同步更新。

## 目录

> 编号是**主题章节号**，与 Day 无对应关系（Day 6 的服务化内容在 05）。

| 文档 | 内容 |
| --- | --- |
| [01-file-inventory.md](01-file-inventory.md) | 全仓库文件清单——每个文件在做什么、属于哪一天的产出（含 Day 7 repair、Day 8 adversarial、Day 9 证据链、Day 10 deploy/、**Day 11 图谱检索、Day 12 multimodal/、Day 13 perf/·repair/tot·validation/parallel**）|
| [02-system-architecture.md](02-system-architecture.md) | 系统架构图、数据流（含修复/对抗评估/证据链/部署/**图谱第三路/多模态入库·问答/性能分片路径**）、模块设计思路、LangChain 使用边界审计、稳健性与适应性评估 |
| [03-config-and-services.md](03-config-and-services.md) | 配置全景图：工程工具链 + 本地 docker 服务（Vespa/Neo4j）+ MiniMax chat/**VLM** API + Day 10 GCP 按需部署拓扑（§7）|
| [04-tech-selection.md](04-tech-selection.md) | 选型说明：每项技术选择的候选、决定、理由与决策出处（至 **Day 13 性能与推理策略选型**）|
| [05-api-and-demo.md](05-api-and-demo.md) | Day 6 服务化：FastAPI + Streamlit 哑客户端、SSE 流式带召回、上传事务化、demo 安全边界;§9 Day 10 公网模式（demo_guard）与按需部署补章 |

## 维护规则

- 每个"重架构日"（Day 4/5/6/8/10/11/12/13）收口时更新对应章节；十三日切片已收口
  （`v1.3.0`），后续任何架构变更以本快照为对照基础；
- 图与文字描述以 **仓库现状** 为准，未实现的目标态一律标注"（Day N 计划）"；
- 与 [docs/constitution.md](../constitution.md) 冲突时，宪法优先。
