# Day 8 会话交接（Handoff）— 2026-07-18

> **AI-generated**（Claude 实现方,session 结束前交接）。目标读者:下一个 AI
> session + Yi Xin。范围:Day 8 已完成部分、收口复盘、Day 9 启动。规则源:
> CLAUDE.md 与 docs/constitution.md。**权威细节以各文档为准,勿仅凭本文摘要行动。**

## 0. 一句话状态

Day 8（评估红队:攻击自己的 RAG）**已完整收口**:实现 + 跨宿主红队全修 + **人工 κ
校准**三段全部完成并合并。**PR #8（实现)+ PR #9（κ 补全)squash 入 `main`、打
tag `v0.8.0`、进度表中英双标 ✅**。268 测试 + 9 skip 全绿,lint 干净,`main` 已同步
origin、工作树干净。**Day 8 结束,下一步 Day 9——从 `main` 新开 `feat/day9`。**

## 1. Day 8 交付了什么

| 交付物 | 位置 | 要点 |
| --- | --- | --- |
| 对抗评估集 | `eval/golden/day8-adversarial.jsonl` | 32 例四类(改写/扰动/无答案/跨文档),LA100 真锚。**AI 起草待审**(每行 `ai_drafted:true`);全英文;绝不进生成 prompt(防泄漏,有测试) |
| 对抗子系统 | `src/learnarken/adversarial/`（judge/score/run/models/`__init__`) | 双异构裁判 + 行为判分 + 交集判定 + Cohen κ + 冻结 artifact |
| CLI | `learnarken eval adversarial` | 活体跑(MiniMax 生成 + Codex/agy 裁判)→ 冻结报告 + per-judge artifact |
| 工具 | `tools/adversarial_eval.py` | `--repeat N`(行为分布,消非确定)+ `--kappa-only`(确定性 κ,无活体) |
| 生成层围栏 | `src/learnarken/answer/prompt.py` | 实体/值对齐 + 禁派生(消除 X-01 聚合缺陷) |
| 依赖 | `pyproject.toml` | 新增 `scikit-learn`(Cohen κ);拽进 numpy/scipy,本仓最重一笔,Yi Xin 同意 |
| 决策链 | `docs/specs/day8.md`、`docs/discussions/day8.md` | 决策层转录 Yi Xin 口述(A–E 二轮裁定)+ 细化层 AI 起草待审 |
| 流程闸产出 | `docs/research/day8-unknowns.md` | 研(在档)→扫(T1–T6 张力) |
| 红队 + 裁决 | `docs/reviews/day8.md` | Part 1（Codex `DO_NOT_MERGE`,13 条)+ Part 2(受指示转录「全接受+已修」) |
| 证据链 | `docs/notes/day8-defects.md` | DR §5「发现→根因→修复→前后对比」四段 + κ 表 |
| κ 校准 | `eval/golden/day8-human-labels.json`(+ worksheet)、`eval/results/day8-kappa.json` | 人工盲标 n=30,κ 结果见 §4b |
| 测试 | `tests/test_day8_adversarial.py` | 22 例:对抗集完整性、行为判分(含否定感知)、裁判交集 fail-closed、严格解析防回显、MiniMax 家族封禁、κ 偏斜陷阱、防泄漏、编排端到端;活体裁判套件 skip |
| 架构文档 | `docs/architecture/01`、`02` | 重架构日:补 Day 7 repair 子系统(§2.8)+ Day 8 adversarial(§2.9)+ 适应性/玩具层表 |
| README | `README.md`/`README.zh-CN.md` | Day 8 对抗评估节(诚实前后对比 + κ)+ 进度表 ✅ |

## 2. 核心设计（面试级,务必记住）

1. **异构双裁判 + 人工 κ 锚定 = 「别用 LLM 验 LLM」的兑现**:生成器是 MiniMax-M3,
   裁判强制换族(**Codex=GPT 系 + agy=Gemini 系**,`FORBIDDEN_JUDGES` 子串封禁
   MiniMax 家族)。裁判不是信任来源,是「加速人工抽查的放大器」;信任来自 Cohen's
   κ 对人工盲标的校准(κ>0.60 软门才可用)。这是 Day 5/6/7「闭环验证/哑客户端/
   确定性校验器」一路的同一立场。
2. **三轴分清(易混)**:①**行为**(应答/拒/澄清 + 禁忌值,`behavior_pass` 自动、
   确定性)②**有据性-裁判**(答案 vs 证据,Codex/agy 自动)③**有据性-人工**(κ 锚,
   人盲标冻结答案 vs 证据)。κ = ③ 校 ② ,验证裁判可信;①是正确性另一轴。
3. **裁判工程纪律(红队逼出来的)**:裁判 error **fail-closed**(不丢弃→该行判非
   grounded);输入**聚光灯**(JSON+随机分隔符+被动数据框定,防注入);严格解析
   +**per-call nonce**(防 CLI 回显指令示例被当裁决);codex 走 stdin(数据不进 argv)。
4. **非确定生成器要重复测**:MiniMax temp=0 仍服务端非确定→行为按 N=3 均值冻结
   artifact(`--repeat`),不报单跑点估计。

## 3. 缺陷 + 修复（诚实版,§4b 有 κ）

- **RCA 先分层,洗清检索层**:候选检索缺陷 X-06 经 trace(`20260718T020117`)证明
  两 DM 的 chunk 都在 top-5,是 MiniMax 非确定漏答,非召回缺失。
- **唯一稳健缺陷 = X-01 跨文档聚合**:问「两处扭矩加起来共多少」,模型算
  25+18=43 Nm(证据没有的派生数)。prompt「禁派生」围栏**确定性消除 3/3→0/3**。
- **诚实修正(INV-7)**:早期用松 scorer + N=3 报过「0.917→0.979」——**已推翻**。
  最终严格 scorer 下**整体行为率持平(0.94→0.93)被非确定主导**;能站住的是 X-01
  确定性消除 + 裁判有据性 0.53→0.63。**别拿整体率当头条**。
- **评估器自身有 bug(自测抓的)**:最初 `behavior_pass` 子串匹配把「不是 30 Nm」
  的纠正误判成「肯定 30」,造假缺陷、污染前后对比;修为**从句级否定感知 + 「是否
  说出正确值」信号**。

## 4. 收口已完成（勿重做）

- **PR #8**（实现,`0ca6cde` squash 入 main):代码 + 全部文档 + 人写 journal。
- **mark-complete `167c14d`**:进度表中英 ✅,**tag `v0.8.0` 打在此提交上**(沿
  v0.5–7 惯例)。
- **PR #9**（κ 补全,`bb0008c` squash 入 main):见 §4b。
- 两个日分支 `feat/day8`、`feat/day8-kappa` **均已删**(一天一分支纪律)。
- `pyproject version` 仍 `0.2.0`(历史与 tag 解耦,沿旧惯例)。

## 4b. κ 校准结果（PR #9,面试金料）

人工**盲标 n=30**(Day5-answered 14 + Day8 对抗答出 16,决策 B,Yi Xin 判 24 true/
6 false):

| 裁判 | κ (n=30) | 一致率 | 软门 0.60 |
| --- | --- | --- | --- |
| Codex | **0.737** | 90% | ✅ substantial |
| agy | **0.667** | 86.7% | ✅ substantial |

**都过门可用,但从 n=16 的 0.85/1.00 回落**——n=16 只覆盖 Day8 干净纠正行偏乐观,
补 Day5(裁判对 C109/C124/C108 判 hallucinated、Q015/Q009/C101/C111 两裁判分歧)后
是更诚实的锚。裁判也补跑了 Day5 答案(verdicts 30 条)。复跑:
`uv run python tools/adversarial_eval.py --kappa-only`(确定性,冻结标签)。

## 5. Day 8 未关的 backlog + 一条教训

- **红队 P3 接受-标注(toy-scale)**:`_contains` 子串匹配(`125 Nm` 满足 `25 Nm`)
  →数字/单位感知匹配挂 Roadmap;裁判 180s 超时无「失败次数硬上限」→熔断挂 Roadmap
  (reviews/day8.md #11/#12)。
- **主 groundedness 报告(0.53→0.63)来自硬化前裁判跑**;Day5 补跑用硬化后裁判。
  硬化改稳健性、非干净输出的裁决值,对比仍成立——若要严格一致可重跑整套(约 30
  裁判调用),已标透明。
- **κ 小样本(n=30)置信区间宽**;更稳需扩标注。
- **journal 表头占位待 Yi Xin 改**:`docs/journal/day8.md` 正文人写,但表头仍模板
  `Day N — <date>`,改成 `Day 8 — 2026-07-18`(AI 不碰 journal)。
- 延续 Day 5/6/7:#8 index epoch / content hash、#9 trace 明文 payload、语义多跳
  (Day 9 依赖查询)。

**一条教训(已入实现方记忆 [[honest-nondeterministic-eval]])**:**评估非确定生成器,
报稳健可复现的缺陷,不报被噪声主导的整体均值;评估器自身也要被评估;诚实数字优先
于好看数字。** Day 8 我主动推翻了自己写的 README 数字——这比留个好看的假数字强。

## 6. Day 9 启动（execution-plan §Day 9,先走每日循环)

**Day 9 = 证据链与机器可读性(`v0.9.0`)。** 范围(execution-plan.md §Day 9 权威):
- **做**:① `docs/EVIDENCE.md`——每条对外声明(简历行/README 数字)→仓库内证据
  (脚本/golden/消融表/trace/κ artifact)映射表,**为审批人 + 招聘方 AI agent 的核查
  路径设计**;② `docs/AI-COLLABORATION.md`——AI-first 工作流说明(SPEC/红队/裁决样例
  + 三道理解闸 + 「哪些必须人做」),**显式用 adversarial validation 术语**并注明与
  ML 传统含义(分布偏移)的区别;③ 根目录 `llms.txt`——给 AI agent 的仓库导览;
  ④ **依赖图查询**(ADR-0002,`docs/adr/0002-*`:图同步已提前到 Day5,本日补依赖
  查询类如「DM X 废弃影响哪些程序」,接口①方向);超时按 INV-8 滑点裁为设计稿;
  ⑤ 复盘 specs/reviews/journal 全目录补漏。
- **证**:陌生 AI agent 只读 `llms.txt` + `EVIDENCE.md` 能 5 分钟内定位任意基准数字
  的复跑方式。
- **注**:Day 8 的 κ artifact + 冻结件(`eval/results/day8-*.json`)是 EVIDENCE.md
  的现成素材。

**每日循环 step 1(研→读→扫,强制)**:研报**在档**
`docs/gemini-deepresearch/day9-AI Verifiable Repo Research.md`(无需重跑);教程
`docs/tutorials/12-interview-prep.md`;Yi Xin 读;AI 写 `docs/research/day9-unknowns.md`。
**再等 Yi Xin 手写 SPEC 决策层**(`docs/specs/day9.md`,AI 不代写),然后实现→**自动
红队闸**→裁决。

**分支纪律(务必)**:`git switch main && git pull` → 从 main HEAD 新开 `feat/day9`;
动手前 `git log --oneline main..HEAD` 核空。

## 7. 环境事实（新 session 无需重建）

- **Vespa**:`learnarken-vespa`,`127.0.0.1:8080/19071`,manifest `.vespa-manifest.json`
  (git-ignored)。语料 43 chunks(package-a + package-c);索引陈旧时
  `learnarken index samples/package-a samples/package-c`(或 `vespa.clear()` 后重索)。
- **Neo4j**:`learnarken-neo4j`,`127.0.0.1:7474/7687`。⚠️ `.env` 只有 `MINIMAX_*`,
  **无 `NEO4J_*`**(容器跑默认凭证)——与旧 handoff 说法有出入,已核。
- **裁判 CLI**:`codex`(exec,GPT 系)、`agy`(Antigravity,Gemini 3.1 Pro)均在;
  **`gemini` CLI 已死**(IneligibleTierError,个人层停用)→ agy 是 Gemini 唯一通道。
- **模型缓存**(~/.cache/huggingface,SHA pin):Qwen3-Embedding-8B、bge-m3、
  bge-reranker-v2-m3。机器 M5 Max/64GB。
- **依赖**:Day 8 加了 `scikit-learn`(Cohen κ);`uv sync` 后可用。
- 验证:`make test`(268+9)、`make lint`;κ:`tools/adversarial_eval.py --kappa-only`。

## 8. 高价值教训（面试素材,journal 可用）

1. **异构 + 人工锚定是裁判合法性的唯一来源**:κ=0.67–0.74 让「裁判可信」有了可审计
   数字,而非信仰;补 Day5 让 κ 从 0.85/1.0 回落到诚实区间——**小样本 + 只测干净行
   会高估裁判**。
2. **跨宿主红队咬到实现方 + 人都漏的洞**:Codex 13 条含「裁判聚合 fail-open」「提示词
   回显可当裁决」「我写的 README 违 INV-5」——印证多智能体对抗设计。
3. **评估器自身要被评估**:一个子串 bug 造出一批假缺陷,差点写进 README。
4. **诚实数字优先**:主动推翻自己的 0.917→0.979,只留 X-01 确定性消除这条硬证据。
5. **能用确定性判分就别用 LLM**:行为判分(应答/拒/禁忌值)全程无 LLM;LLM 只用在
   语义有据性,且被 κ 关进笼子。
