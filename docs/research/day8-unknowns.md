# Day 8 未知点扫描 — 评估红队：攻击自己的 RAG

> **AI-generated**（Claude 实现方，2026-07-17，研→读→扫 第三步）。交叉引用：
> `docs/gemini-deepresearch/day8-RAG对抗评估深度调研.md`（官方 DR 报告，
> 2026-07-15 生成）、tutorials/05-rag.md §4（引用与 Groundedness）、
> execution-plan.md §Day 8、docs/handoff/day7.md §6。按 Anthropic
> "Finding Your Unknowns" 四象限做盲区扫描。
>
> **边界声明**：本文只做扫描与深讲，**不代写 SPEC 决策层**。文末「待决策层拍板
> 的张力」列出的都是判断题，等 Yi Xin 手写 `docs/specs/day8.md`——有歧义先问，
> 不猜（CLAUDE.md 角色边界 / INV-6）。

## 本项目的落地锚点（不是通用 KB，别照搬 DR 报告的例子）

DR 报告的 30 例对抗集是通用企业库（IT 支持 / 财务政策 / 硬件参数）。**我们的库是
LA100 航空维修 S1000D 合成语料**（`samples/package-a`、`samples/package-c`），
现成的攻击素材已在仓库里：

- **真零件号 / 编码**：`LA-29-4711-1`（液压泵 P/N）、`DMC-LA100-A-29-10-00-00A-941A-D`、
  `ICN-LA100-29-001-02`——扰动敏感性(字符级 Fuzzing)的天然靶子。
- **真数值**：可见镀铬 55–65 mm、扭矩 18 Nm / 25 Nm、四颗安装螺栓、先断负极——
  事实矛盾 / 局部幻觉的靶子。
- **Day 5 已埋的 no-answer trap**：Q021 cabin pressurization、Q023 de-icing boot、
  C149 fuel quantity（库里没有的系统）——无答案陷阱的现成种子。
- **Day 5 答案层三道 fail-closed 闸**（`src/learnarken/answer/engine.py`）：
  threshold(重排分数) → llm(`is_answerable`+契约) → citation-validation(逐字子串)。
  **对抗集要测的是：每一类攻击被哪道闸拦下，或从哪道闸漏过去。**

## 象限扫描

### 已知的已知（今天要动手的）

- **对抗集 ≥30 例，四类**：改写不变性 / 扰动敏感性 / 无答案陷阱 / 跨文档(跨模块)
  混淆。DR §3 建议配比 20/30/25/25，但**要用 LA100 语料重造**（INV-1 合成、
  INV-3 枚举、每类附 expected behavior）。DR 30 例是模板不是数据。
- **LLM-as-judge groundedness**：extraction+verification 双步（把答案拆成原子
  声明，逐条对检索上下文核验；得分=获支持声明/总声明）——DR §4、tutorial 05 §4。
  单点打分制（避免位置偏差），非成对比较。
- **judge × 人工一致率校准**：execution-plan §Day 8 硬性要求「不许只报 judge
  数字」。这是 INV-6「红队数字人复跑」在评估层的兑现。
- **修 ≥2 个真实缺陷 + 前后指标对比进 README**（INV-5 可复跑、INV-7 诚实分层）。
- **一条命令复跑**对抗评估（延续 `tools/answer_sample_eval.py`、
  `tools/measure_refusal_threshold.py` 的固定 seed + 落 artifact 模式）。
- **重架构日欠账**：把 Day 7 `repair/` 子系统 + Day 8 评估工作补进
  `docs/architecture/01`、`02`（handoff §4b，非遗漏，是按 cadence 延后到今天）。

### 已知的未知（动手前必须由决策层定 —— 见文末张力清单）

1. **校准锚点从哪来（最关键）**。Day 5 的 20 例
   `eval/results/day5-answer-sample.json` 里 `human_review: "pending"`——
   engine 自己标注「supporting_quote 子串是机器地板，语义 groundedness 是人的
   一步」。**Day 8 的 judge 要与「人工」对齐，但那批人工 groundedness 标签目前
   尚不存在。** 是先补 Day 5 那 20 行的人工盲评做锚，还是给 Day 8 新对抗集造
   一批人工标签？谁标、标多少、标哪批——决策题。
2. **Judge 模型异构性**。生成器是 MiniMax-M3（`src/learnarken/llm/minimax.py`，
   `.env` 只有 `MINIMAX_*`）。DR §6/§7 铁律：**禁止同源模型当裁判**（self-preference
   bias，对自产幻觉盲目认同）。可选：(a) 换 MiniMax 别的变体=弱异构；(b) 引入
   另一家 API（当前无 key）；(c) 接受同源 + 强人工锚定 + 显式标注 caveat。
   这正是 handoff §6 点名、Day 7 报告 §5.4 警告的「生成器-验证器共谋」张力。**不由 AI 决定。**
3. **一致率用什么统计量**。DR §4 力主 **Cohen's Kappa > 0.60**（惩罚偶然一致，
   给了 85% raw agreement → κ=0.167 的反例）；tutorial 05 §4 只说「报一致率」。
   仓库**无 sklearn/scipy/numpy**——Kappa 要么 DIY（2×2 公式很简单）要么加依赖。
   样本量小（若只锚 20 例）κ 置信区间很宽，报不报 CI？
4. **对抗集谁写、expected 谁定**。Day 3 先例（execution-plan §Day 3）：
   「标注必须人做，AI 只许起草候选问题」。对抗 expected behavior（应答/应拒/
   应澄清）是判断力所在。沿用「AI 起草 30 候选、人确认 expected」还是人主导？
5. **对抗集落哪、如何防泄漏**。现有 golden 在 `eval/golden/*.jsonl`。对抗集是新
   文件（如 `eval/golden/day8-adversarial.jsonl`）？**物理隔离怎么保证**——绝不
   进 prompt / few-shot / 任何生成端（DR §7 坑1，「背考题」假涨分）。
6. **「真实缺陷」如何界定 + 修在哪一层**。≥2 个缺陷指评估暴露的系统缺陷（如
   零件号扰动不拒答）。修法走 prompt guardrail（DR §5.3 案例：System Prompt 注入
   实体对齐围栏 + 降温）便宜但可能治标；DR §7 坑3 警告「只修指标不修根因」
   （chunking / 过期数据才是病灶）。修哪层是判断题。

### 未知的已知（容易带错的旧直觉）

- **「Day 5 指标满分 = 系统可靠」是假安全感**。Day 5 sample：answerable_success
  0.875、trap_refusal 1.0、citation_coverage 1.0——但那是 20 例 happy-path。
  DR §1：平均指标幻觉。对抗集专攻分布边缘，指标**必然掉**；掉下来才是 Day 8
  的价值，不是失败。
- **「supporting_quote 子串命中 = grounded」错**。子串是**机器地板**≠语义有据。
  局部幻觉（几条对里掺一条错）、范围扩张（A 规则套到 B）照样过 Day 5 的
  citation-validation 闸。语义蕴含正是 engine.py:235 自己标注「semantic
  entailment is Day 8」的靶心——Day 5 埋的坑，Day 8 兑现。
- **「temperature=0 → 确定」错**。judge 打分仍非逐字节确定（延续 day5-unknowns
  的结论）。测试断言结构（获支持声明数、pass/fail 布尔），不断言 judge 全文。
- **「judge 打高分 = 答得好」错**。LLM 裁判有过誉倾向 + 冗长偏好 + 自恋偏差
  （DR §4）。长篇废话盖住一句「未提及」也可能被判高分——所以必须 Kappa 而非
  raw agreement，异构而非同源。

### 未知的未知（预埋观测点）

- **对抗集数据泄漏**（DR §7 坑1）：修 prompt 时若把对抗样本当反例写进 few-shot →
  回归「背考题」假涨分。**埋点**：对抗 golden 与 prompt 物理隔离，加一条 CI/测试
  断言 prompt 模板里不含对抗集字符串。
- **修 guardrail 引发正常路径回撤**（DR §5.3 remediation 的隐性代价）：加实体
  对齐围栏可能把本可答的 answerable 变误拒。**埋点**：任何修复后必须在 Day 5 的
  16 个 answerable 上回归，报 `false_refusal_rate` 前后——别用「拒答变严」换
  「假拒变多」。
- **归因到具体防线**：零件号扰动可能连 threshold 闸都过（embedding 对连续字符
  不敏感，向量距离太近，DR §5.1 根因）。**埋点**：trace 已记 `top1_score` 和
  `refusal_gate`——统计每类攻击被 threshold / llm / citation 哪道闸拦，缺陷才能
  定位到层。
- **judge prompt 敏感 / 漂移**：judge prompt 微调即改分。**埋点**：judge prompt
  版本化 + 固定 seed + judge 的 CoT 理由落盘，κ 复算可追溯。

## 必须吃透的点（面试级）

1. **为什么「只报 judge 平均分」是工程欺诈——Cohen's Kappa 的锁**。
   DR §4 的残酷案例：100 例里人工判 90 Pass/10 Fail，未调优 judge 也打 90/10，
   表面 raw agreement 85%，但因双方都极度偏向 Pass，纯随机一致率就有 0.82，
   **κ 只有 0.167（极微弱一致）**——judge 根本没理解 groundedness，只是在盲目
   点赞。类别不平衡 + 过誉倾向下，raw agreement 系统性骗人。κ>0.60 才允许把
   judge 并入自动流水线。**这是 judge 合法性的唯一数学来源**，也是 handoff §6
   点名的 Day 8 最佳面试素材。

2. **生成器-验证器共谋 vs 本项目一路的闭环验证立场**。Day 5（确定性引用确证）、
   Day 6（哑客户端）、Day 7（XSD/BREX 死板校验器、「绝不用 LLM 验 LLM」）是同一
   立场。Day 8 偏要引入 LLM judge——**正解不是背叛该立场，而是把 judge 关进
   笼子**：judge 只是「加速人工抽查的放大器」，不是信任来源；异构（换模型族）
   + 人工锚定（κ 校准）是笼子，κ 是锁。这条张力（异构验证 + 人工锚定 ≠ 盲信
   judge）是 Day 8 最好讲的故事。

3. **语义 groundedness = Day 5 埋的坑的兑现**。Day 5 的 citation-validation 只卡
   「引用逐字出现在被检索 chunk 里」这一**必要条件**；**充分性**（引用是否真的
   支撑答案）留给 Day 8。judge 的 extraction+verification 双步测的正是这个：把
   答案拆成原子声明，逐条问「能否从证据推出」。四类失效——纯捏造 / 事实矛盾 /
   局部幻觉 / 范围扩张——要对应到 LA100 域的具体样本（如把 55–65 mm 篡改成
   50 mm、把 LA-29-4711-1 参数嫁接给 -2）。

4. **对抗四类 × 我们 S1000D 域的映射（照搬 DR 例子会跑偏）**。
   - **改写不变性**：口语化 / 跨语言（中问英答）/ 去标点 问同一维修步骤，答案核心
     语义不变。
   - **扰动敏感性**：零件号 `LA-29-4711-1`→`-2`、DMC 段位改一位、扭矩 18→19 Nm。
     健康系统**必须拒答**，严禁用旧号参数糊弄。
   - **无答案陷阱**：库里没有的系统（cabin pressurization / de-icing / fuel
     quantity 已是 Day 5 trap 种子）+ 错误前提提问（「第 4 步注意什么」而文档只有
     3 步）。
   - **跨文档混淆**：多 DM 召回、VIO-6 跨域（船舶模块混进飞机库）、同名不同版本
     DM（issueInfo 冲突，对应 VIO-5）——测属性嫁接 / 版本意识。
   INV-1 全合成、INV-3 每类枚举编号 + golden 对。

## 待决策层拍板的张力清单（等 Yi Xin 手写 SPEC，AI 不代答）

| # | 判断题 | 相关约束 / 素材 |
| --- | --- | --- |
| T1 | 校准锚点：补 Day 5 那 20 行人工 groundedness 标注，还是给 Day 8 对抗集新造人工标签？谁标、标多少？ | day5-answer-sample.json `human_review: pending`；INV-6 |
| T2 | Judge 用哪个模型？异构(换族/无 key) vs 同源+人工锚定+caveat？ | DR §6/§7；handoff §6；`.env` 只有 MINIMAX_* |
| T3 | 一致率报 raw agreement 还是 Cohen's Kappa（>0.60 门）？小样本报 CI 吗？无 sklearn，DIY 还是加依赖？ | DR §4；tutorial 05 §4；pyproject 无 sklearn/scipy |
| T4 | 对抗集 expected behavior 人定还是 AI 起草人确认？ | Day 3 先例「标注人做」 |
| T5 | ≥2 个「真实缺陷」的界定与修复层（prompt guardrail vs 检索/chunking 根因）？ | DR §5.3 / §7 坑3 |
| T6 | 对抗集落盘位置 + 防泄漏机制（不进 prompt/few-shot）？ | DR §7 坑1；eval/golden/ 现有布局 |
