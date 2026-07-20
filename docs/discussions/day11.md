# Day 11 讨论备忘：SPEC 生成与两项裁决

> **AI-distilled**（Claude，2026-07-19，待人审）。同日 SPEC 生成会话中的
> 决策记录；上游范围决策见 [day11-13-planning.md](day11-13-planning.md)。

## 背景

Yi Xin 以书面指令给出 Day 11 决策层三点要求（确定性实体链接器 / `CITES` 边
1–2 跳图谱扩展进 RRF 第三路 / 新建多跳评估集 + hybrid vs hybrid+graph 消融
诚实报告），AI 据此转录生成 [specs/day11.md](../specs/day11.md)（决策层转录、
细化层 AI-drafted 待批）。起草时发现两处需人裁决，同日裁掉：

## 裁决

1. **边 schema：用现有 `:REFS`，不改名 `CITES`**。指令原文写 `CITES`，仓库
   Neo4j 现有 schema 是 Day 9 的 `(:DM)-[:REFS]->(:DM)`（语义相同：引用/
   依赖）。改名会牵动 Day 9 影响查询、测试与冻结证据，无行为收益。
   裁决原话："使用 :REFS"。

2. **多跳出题人：选项 (a)，Yi Xin 亲自出题**。T4 防循环红线要求出题人不看
   边清单；AI 起草 candidates 的既有流程（Day 3/4）会削弱盲测保证，故弃
   选项 (b)。出题存档位置：
   [eval/golden/day11-multihop.worksheet.md](../../eval/golden/day11-multihop.worksheet.md)
   （模板脚手架 AI 生成，题目内容人写；AI 事后只校验锚点跨 ≥2 个引用相连
   DM 并格式化为 jsonl，不改题不补题）。

## 影响

- SPEC 两处已回写留痕（schema note 标 RULED；开放问题标 RULED，原文折叠
  保留 provenance）。
- 实现可开工；golden 集环节等 worksheet 填写完成后进入锚点校验。
