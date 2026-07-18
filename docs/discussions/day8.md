# Day 8 设计讨论蒸馏 — 评估红队

> **AI-distilled**（Claude 实现方，2026-07-17，同 session 蒸馏；INV-6：AI 蒸馏、
> 标注、待 Yi Xin 复核）。来源：day8-unknowns.md 的 T1–T6 张力 + Yi Xin 2026-07-17
> 的三条口述指示。格式：问题 → 选项 → 决定 → 理由。决策层权威见
> [docs/specs/day8.md](../specs/day8.md)。

## D1（T2）裁判用什么模型 —— 生成器-验证器共谋

- **问题**：Day 8 要引入 LLM-as-judge，但生成器是 MiniMax-M3，且本项目一路
  "绝不用 LLM 验 LLM"（Day 5/6/7）。同源裁判会 self-preference 共谋（DR §6/§7）。
- **选项**：(a) MiniMax 别的变体=弱异构；(b) 引入另一家 API（无 key）；
  (c) 同源+人工锚定+caveat；(d) 用订阅制 CLI（Codex/Gemini/Claude）当裁判。
- **决定（Yi Xin）**：走 (d)，且**同时用 Codex 与 Gemini 双裁判**，**禁用
  MiniMax**。裁判 ⟂ 生成器，且两家不同族——**它们的分歧本身是信号**，要报出来。
  建议裁判也 ⟂ 实现方（不用 Claude），保持异构故事最干净。
- **理由**：异构防偏是裁判合法性的前提（DR §6）；双裁判把"单点黑盒打分"变成
  "两个独立红队 + 分歧可见"，正是本项目一贯的异构验证立场，不背叛"别用 LLM 验
  LLM"，而是把 judge 关进"异构+人工锚定"的笼子。

## D2（T2/顾虑2）CLI 裁判的可复现性

- **问题**：CLI 订阅制无法 pin seed/模型版本，活体重跑 judge 可能漂，冲突 INV-5
  "每个 README 数字要有可复跑命令"。
- **决定（Yi Xin，建议认可待确认 E/D）**：judge 每例输出**冻结成 committed
  artifact**（`eval/results/day8-judge-<name>.json`，记 model+version+date）；
  README 数字锚冻结件；复跑命令跑"冻结标签 → κ 计算"这段（确定性）。judge 调用
  像人工标注一样冻住、不每次现算。裁判以**受约束单发 JSON 模式**驱动，不放成
  自主 agent（Day 7 教训 5）。
- **理由**：把不确定的上游（judge 调用）冻结为证据，INV-5 经 artifact 兑现，与
  "红队数字合并前人工复跑/锚定"（INV-6）同构。

## D3（T3）一致率的统计量 + 依赖

- **问题**：报 raw agreement 还是 Cohen's Kappa？仓库无 sklearn/scipy/numpy。
- **决定（Yi Xin）**：**加依赖**，用 `sklearn.metrics.cohen_kappa_score`。报 κ，
  不许只报 raw agreement。
- **理由**：偏斜的全 pass 集下 raw agreement 骗人（DR §4 的 85%→κ=0.167）。κ 扣掉
  偶然一致，是 judge 合法性的数学锁。代价：sklearn 拽进 numpy+scipy（本仓最重一笔
  依赖）——Yi Xin 明确同意。

## D4（T1/顾虑1）人工校准锚从哪来

- **问题**：Day 5 的 20 例 `human_review` 已由 Yi Xin 看过/通过——但 happy-path
  很可能**全 pass**，无类别方差 → κ 退化无意义（DR §4 偏斜陷阱）。
- **决定（Yi Xin）**：**混合** Day 5 已复核样本 + Day 8 对抗集的人工标注标准做锚。
- **理由**：对抗集本就产生一批 pass + 一批 fail，方差回来了，κ 才有意义。
- **留待确认（SPEC 开放项 B）**：Day 5 那 14 个 answered 行里有没有人工判 fail 的？
  anchor 全集与样本量 n 待 Yi Xin 定死。

## D5（T4）对抗集与 expected 谁写

- **问题**：Day 3 先例"标注人做，AI 只起草"。对抗 expected（应答/拒/澄清）是判断力。
- **决定（Yi Xin）**：**对抗集 + expected 由 AI 设计，Yi Xin review**（INV-6 细化层，
  复核后生效）。**groundedness 的人工锚标签仍归人**——两者不混（题面设计 vs 答案有据性）。
- **理由**：题面设计可委托并复核；κ 的人工锚是信任来源，不可外包。

## D6（T5）缺陷先分因再修

- **问题**：≥2 个真实缺陷，修在哪一层？
- **决定（Yi Xin）**：**先做根因归类——提示词层 vs 检索/根因层——再修**。修完
  **用同样攻击复跑 judge 验证完整修复，不许自认为修好**（regression gate，D 无自证）。
- **理由**：DR §7 坑3"只修指标不修病灶"；DR §5 分检索层失效 vs 生成层失效。复验闸
  防"改了 prompt 就宣布完成"的假收口。

## D7（T6）对抗集落盘 + 防泄漏

- **问题**（Yi Xin 曾问没看懂）：对抗集存哪、怎么防泄漏。
- **决定（Yi Xin）**："该落盘的落盘"——存 `eval/golden/`（版本化，同 day3/4）。
  **绝不进答案生成的 prompt/few-shot**，加测试/CI 断言隔离。
- **理由**：对抗题进 few-shot = 系统"背考题"过关，指标是假的（DR §7 坑1）。

## 附：与前几日的呼应（面试素材）

- **语义 groundedness = Day 5 埋的坑兑现**：Day 5 引用确证只卡逐字子串（必要条件），
  Day 8 judge 的 extraction+verification 测充分性（引用是否真支撑），抓捏造/矛盾/
  局部幻觉/范围扩张（engine.py:235 自标 "semantic entailment is Day 8"）。
- **双裁判分歧 = 异构验证具象化**：呼应 Day 7 报告 §5.4"换模型族看同一段"。
