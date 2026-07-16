# 架构文档（Architecture）

> **AI-drafted**（Claude，实现方助手），基于 Day 1–3 已合并/在途代码、docs/specs、
> docs/discussions、docs/reviews 与 docs/local-services.md 蒸馏，**待 Yi Xin 审阅**。
> 快照日期：2026-07-15（Day 4 启动前）。本文件夹只记录"已经是什么、为什么这么选"，
> 不做新决策；所有决策出处均给出链接。

## 这个文件夹是干什么的

1. **解释与演示**：向读者（自己、面试官、招聘方的 AI agent）解释每个文件/模块的
   设计思路与架构细节；
2. **评估基线**：评估当前架构的适应性（能不能接住 Day 4–10 的增量）与稳健程度
   （哪些是工程化的、哪些是玩具层，诚实分层 INV-7）;
3. **变更基准**:后续任何架构变更（换向量库、加图查询、改分块策略）以本文件夹的
   快照为对照基础，变更时同步更新。

## 目录

| 文档 | 内容 |
| --- | --- |
| [01-file-inventory.md](01-file-inventory.md) | 全仓库文件清单——每个文件在做什么、属于哪一天的产出 |
| [02-system-architecture.md](02-system-architecture.md) | 系统架构图、数据流、模块设计思路、稳健性与适应性评估 |
| [03-config-and-services.md](03-config-and-services.md) | 配置全景图：工程工具链 + 本地 docker 服务（Vespa/Neo4j）+ MiniMax API |
| [04-tech-selection.md](04-tech-selection.md) | 选型说明：每项技术选择的候选、决定、理由与决策出处 |

## 维护规则

- 每个"重架构日"（Day 4/5/8）收口时更新对应章节；
- 图与文字描述以 **仓库现状** 为准，未实现的目标态一律标注"（Day N 计划）"；
- 与 [docs/constitution.md](../constitution.md) 冲突时，宪法优先。
