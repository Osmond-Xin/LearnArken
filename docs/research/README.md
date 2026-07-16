# docs/research/ — 每日领域深度调研与未知点扫描

> 学习流程 v2 的产物目录（2026-07-15 起，Day 4 生效；决策记录见
> [discussions/day4.md](../discussions/day4.md)）。方法论来自 Anthropic
> 《A Field Guide to Claude Fable: Finding Your Unknowns》：把 unknown
> unknowns 显式化，先建领域全景、再扫盲区、后实践。

## 每日两份文件

| 文件 | 内容 | 生成方 |
| --- | --- | --- |
| [`../gemini-deepresearch/dayN-*.md`](../gemini-deepresearch/) | 当日领域深度调研（中文）：背景、发展源流、主流特色、未来方向、最佳实践、必会技巧与坑。**Day 1–10 全套已于 2026-07-15 生成**，Claude 审阅结论见 [REVIEW.md](../gemini-deepresearch/REVIEW.md) | Gemini Deep Research（官方，Yi Xin 手动跑）；兜底 `agy` + Gemini 3.1 Pro，须标注「模拟」 |
| `dayN-unknowns.md`（本目录） | 未知点扫描（blind spot pass，按未知象限分类）+ 必会知识点深讲，对照调研报告与当日教程 | Claude（实现方 AI），标注 AI-generated |

## 调研通道（2026-07-15 验证结论）

1. **首选：Gemini 客户端手动跑官方 Deep Research**（2026-07-15 定为主通道）——
   每日提示词已备好：[tutorials/deep-research-prompts.md](../tutorials/deep-research-prompts.md)
   （Day 1–10 全套，自包含、直接粘贴）。Yi Xin 粘贴提示词 → 跑 Deep Research →
   下载报告存为 `dayN-report.md`，文件头加一行
   `> 来源：Gemini App Deep Research，日期 YYYY-MM-DD。`
   自动化备选：Interactions API（agent `deep-research-preview-04-2026`，脚本
   [tools/deep_research.py](../../tools/deep_research.py)），需付费级
   `GEMINI_API_KEY`（免费层无权限），本机尚未配置。
2. **兜底：`agy`（Antigravity CLI）** — `agy --model "Gemini 3.1 Pro (High)"
   -p "$(cat prompt.txt)"`，单次联网调研。它不是多步自主探索的 Deep
   Research，产物开头必须标注「模拟」。
3. **不可用：`gemini` CLI** — 个人免费层（Code Assist for individuals）已被
   Google 停用（IneligibleTierError，指向 Antigravity 迁移），且官方 DR agent
   也不经由该 CLI。

## 定位

本目录是学习资产（AI-generated, labeled），不属于证据链的人写部分——
journal / SPEC 决策层 / 裁决仍由人写，规则见 [CLAUDE.md](../../CLAUDE.md)。
