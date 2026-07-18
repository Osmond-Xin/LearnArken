# Day 7 会话交接（Handoff）— 2026-07-17

> **AI-generated**（Claude 实现方，session 结束前交接）。目标读者：下一个
> AI session + Yi Xin。范围：Day 7 已完成部分、合并收口清单、Day 8 启动。
> 规则源：CLAUDE.md 与 docs/constitution.md。**权威细节以各文档为准，勿仅凭
> 本文摘要行动。**

## 0. 一句话状态

Day 7（自愈修复 Agent：LLM 主导 ReAct + 受约束工具 + 沙箱执行器）**已完全收口**：
实现完成、跨宿主红队（Codex）已跑、16 条 findings 全部已修、扫描已补、人写
journal + Day 6 裁决已提交、**已合并入 `main`（PR #6 = Day 6+7 代码，PR #7 =
收尾）、打 tag `v0.6.0`/`v0.7.0`、中英进度表双双标完成**。246 测试 + 8 skip 全绿、
lint 干净、沙箱 live 验证过。本地 `main` 已同步 origin、工作树干净。
**Day 7 结束,下一步 Day 8——从 `main` 新开 `feat/day8`。**

## 1. Day 7 交付了什么

| 交付物 | 位置 | 要点 |
| --- | --- | --- |
| 修复 Agent 全套 | `src/learnarken/repair/`（models/config/sandbox/patch/tools/prompt/agent/apply/core + `__init__`） | ReAct 循环 + 6 个受约束工具 + 沙箱 + 结构化 EditOp + 批准后写入 |
| CLI `repair` 子命令 | `src/learnarken/cli.py` | 默认 dry-run、`--apply`（逐 patch 人工闸）、`--only`、`--max-iterations/--max-tokens`、`--report`、退出码 0/3/1/2 |
| 预算/沙箱配置 | `pyproject.toml [tool.learnarken.repair]` | 迭代/token/no-progress + sandbox 超时/内存/白名单，可配、加载时钳位 |
| 决策链 | `docs/specs/day7.md`、`docs/discussions/day7.md` | 决策层转录 Yi Xin 三裁决 + 细化层 AI 起草待审 |
| 流程闸产出 | `docs/research/day7-unknowns.md` | 研（在档）→扫（回溯性，标注红队补了扫描盲点） |
| 红队 + 裁决转录 | `docs/reviews/day7.md` | Part 1（Codex `DO_NOT_MERGE`，16 条）+ Part 2（转录裁决，标 provenance，数字复跑留人） |
| 测试 | `tests/test_day7_repair.py`、`test_day7_sandbox.py` | VIO 金对、沙箱逃逸、预算熔断、apply 批准/拒绝、恢复、over-repair 门（24 个） |
| README 更新 | `README.md`、`README.zh-CN.md` | Roadmap Implemented/Toy-scale + 仓库导览 + Quickstart 补 Day 5/6/7；zh-CN 进度表 Day 3/4/5 补勾 |

## 2. 核心设计（面试级，务必记住）

1. **闭环验证 = 唯一信任来源 + 生成器-验证器不共谋**：patch 只在**确定性校验器
   复跑通过**时采信,judge 是死板的 XSD/BREX 解析器、**绝不用 LLM 验 LLM**（报告
   §3.3/§5.4）。这是 Day 5 引用确证、Day 6 哑客户端同一立场——保证放结构里。
2. **神经符号分工**：LLM 只出扁平意图（4 个 `EditOp`：set_attr/set_text/
   remove/insert + 单节点 xpath）,lxml 做 DOM 拼接——消灭「忘了闭合标签」类崩溃。
   **绝不给自由字符串/正则替换工具**（ACI 防呆,报告 §3.1）。
3. **三维熔断防死循环**：迭代/token/no-progress 断路器,可配可钳位（报告 §5.1）。
4. **apply=批准后写入**（Ruling 1 / 宪法 §1.3）：默认 dry-run,`--apply` 逐 patch
   人工闸,原子换入 + journal 恢复 + TOCTOU 复检。**绝不静默改数据**。
5. **风险分级**：高风险类（L0 语法/L1 结构/VIO-6 跨域）强制 dry-run-only,所有
   枚举 VIO 类 apply-eligible;tier 在 apply 边界按 rule_id 重算、不信任存值。

## 3. 红队全部已修（16 项，Yi Xin 指示「修正红队指出的问题」）

Codex 跨宿主判 `DO_NOT_MERGE`。**CLI + 自家 M3 正常路径可达的真洞**：#1 沙箱
python 经 pathlib/lxml 读写任意文件+联网(白名单漏)、#2 shell 参数未 jail、
#4/#5 target 由 LLM 控 + 打补丁文件与报告文件可背离、#8 mem_mb 死配置、#9
finding_key 丢重。#3/#6/#10/#11/#15 设敌意包或直连 API 调用者（§2 非敌意输入
假设部分排除）。**全部已修**（逐条对应见 reviews/day7.md Part 2）；核心修法：
去 pathlib/sys + 禁文件/网络属性、shell 参数 jail、拒符号链接、target 服务端
绑定、apply 边界重算 tier + 文件名 jail + TOCTOU 复检 + journal 恢复、setrlimit、
finding_key + Counter 多重集、参数钳位。**未应用任何修复前先跑红队闸——裁决先
于修复**（本次裁决由 Yi Xin 指示转录,数字复跑仍留人）。

## 4. 收口已完成（复盘 + 一条教训，新 session 无需重做）

Day 6/7 的合并链已全部走完，**不要重做**：

- **PR #6**（`feat/day6` → `main`，merge-commit `ddd6c9c`）：带 Day 6（5 提交）
  + Day 7（2 提交），用 merge 而非 squash 以保留各天历史。PR 描述里写明了
  「为什么没有独立 Day 6 PR」——Day 7 在 Day 6 合并前就在 `feat/day6` 上开发,
  两天绑定落地。
- **PR #7**（收尾，merge-commit `4a01e86`）：人写证据链（`journal/day6.md`、
  `journal/day7.md`、`reviews/day6.md` Part 2 裁决——内容 Yi Xin 写、AI 只提交）
  + 中英进度表 Day 6/7 标 ✅。
- **Tag**：`v0.6.0` → `1a8fc97`（mark day 6 complete）、`v0.7.0` → `a48d8eb`
  （mark day 7 complete），沿用 v0.5.0「tag 打在标记完成提交上」的惯例，均已 push。
- **裁决复核（仍留 Yi Xin）**：`docs/reviews/day7.md` Part 2 是**受指示转录**的
  「全接受+已修」，INV-6 的「红队数字合并前人工复跑」名义上仍是人的责任——已合并,
  若要严格补一次复跑记录可回填。
- **pyproject version** 仍 `0.2.0`（历史与 git tag 解耦，沿旧惯例）。

**一条教训（已写入实现方记忆，务必遵守）**：**绝不在上一天的分支上开发下一天。**
Day 7 直接在 `feat/day6` 上开发,导致 Day 6+7 分支纠缠、只能绑定合并。**Day 8
起：先从 `main` HEAD 新开 `feat/dayN` 再动手；实现前用 `git log --oneline main..HEAD`
核对本分支只含当天内容。**

## 4b. 架构文档欠账（Day 8 重架构日一并补）

Day 7 的 `repair/` 子系统（9 个模块 + `repair` CLI）**尚未进架构文档**
（`docs/architecture/01-file-inventory.md`/`02-system-architecture.md`）。按维护
规则「重架构日 4/5/6/8 收口更新」,**Day 8 就是下一个重架构日**——届时把 Day 7
repair 子系统 + Day 8 评估工作一并补进 01/02。当前是**有意按 cadence 延后**,非遗漏。

## 5. Day 7 未关的 backlog（延续，勿遗忘）

- **多 finding 同文件的拓扑依赖排序**（报告陷阱 2）：当前逐 finding 独立修、apply
  时同文件多 EditOp 顺序叠加;相互依赖的修复顺序可能不对。demo 语料小未触发。
- **投毒上下文**（报告 §5.3）：`search_corpus` 只检索包自身,存在「拿同样错的兄弟
  当范本」风险;当前无置信度评估协议。
- **沙箱 OS 级逃逸**：应用层白名单挡不住原生逃逸（恶意 C 扩展等）;真上生产换
  nsjail/容器/seccomp。已标 toy-scale。
- **best-result 保留**（报告 §5.1）：熔断返回 REFUSED,未返回「触发错误最少的中间
  版本」。多步修复变常见时值得加。
- 延续 Day 5/6：#8 index epoch / content hash、#9 trace 明文 payload、#10 路径
  假设源码布局、#11 `_sanitize` 漏 Unicode bidi。
- **语义 groundedness**（引用蕴含判定）归 **Day 8** 对抗评估,非遗漏。

## 6. Day 8 启动（execution-plan §Day 8，先走每日循环）

**Day 8 = 评估红队:攻击自己的 RAG（`v0.8.0`）⚑ 重型红队节点 + 重架构日。**
范围（execution-plan.md §Day 8 权威,勿凭本文行动）：
- **学**：复习 tutorials/05-rag.md 的评估节（非新教程）。
- **做**：① 对抗评估集 ≥30 例（同义改写、跨模块陷阱、无答案陷阱、零件号扰动）;
  ② **LLM-as-judge** 自动 groundedness 评分 + **与 Day 5 人工抽查对齐校准**
  （必须报 judge×人工一致率,**不许只报 judge 数字**）;③ 修复 ≥2 个红队暴露的
  真实缺陷,前后指标对比进 README。
- **证**：对抗评估一条命令复跑;「发现缺陷→修复→指标变化」完整证据链（INV-5）。

**每日循环 step 1（研→读→扫,CLAUDE.md 强制）**：研报在档
`docs/gemini-deepresearch/day8-RAG对抗评估深度调研.md`（2026-07-15 生成,无需重跑,
缺则请 Yi Xin 跑官方 DR 或 `agy` 兜底并标「模拟」）;Yi Xin 读报告+教程 05;AI 写
`docs/research/day8-unknowns.md`（未知点扫描,AI 生成、标注）。**再等 Yi Xin 手写
SPEC 决策层**（`docs/specs/day8.md`,AI 不代写决策）,然后实现→**自动红队闸**→裁决。

**两处与 Day 7 的呼应（面试级,值得在扫描里点出）**：
1. **语义蕴含判定**：Day 5/6/7 的引用确证只卡「逐字子串」这一必要条件,**语义
   groundedness（引用是否真的支撑答案）是 Day 8 的核心**——Day 5 就埋了这个坑。
2. **LLM-as-judge vs 生成器-验证器共谋**：Day 7 报告 §5.4 警告「别用 LLM 验 LLM」;
   Day 8 偏偏要引入 LLM judge 评 groundedness——**正解正是 execution-plan 要求的
   「与人工对齐校准、报一致率」**,即异构验证 + 人工锚定,而非盲信 judge。这条张力
   是 Day 8 最好的面试素材。

## 7. 环境事实（新 session 无需重建）

- **Vespa**：`learnarken-vespa`，`127.0.0.1:8080/19071`，manifest 在
  `.vespa-manifest.json`（git-ignored）。
- **Neo4j**：`learnarken-neo4j`，`127.0.0.1:7474/7687`，凭证从 `.env` `NEO4J_*`。
- **本地模型**（~/.cache/huggingface，SHA pin）：Qwen3-Embedding-8B、bge-m3、
  bge-reranker-v2-m3。机器 M5 Max/64GB。
- **Day 7 无新第三方依赖**（复用 lxml/pydantic/既有栈;沙箱用 stdlib
  ast/subprocess/resource）。repair 报告落 `eval/repairs/`（git-ignored,与
  traces 同规矩）。
- 验证：`make test`、`make lint`；沙箱 live 抽查见 reviews/day7.md Part 2 头注。

## 8. 高价值教训（面试素材，journal 可用）

1. **「一个被允许的 import 就是一份能力」**：沙箱白名单要按「这库能做什么 I/O」
   审,不是按「看起来人畜无害」。我把 pathlib/lxml 放白名单、以为 AST 挡住
   open/socket 就够——红队证明 `pathlib.Path.write_text`/`lxml.etree.parse(url)`
   经**被允许的库**照样越界。能讲成「建沙箱→红队证明漏→按能力重审白名单」的完整
   故事,比只说「加了沙箱」强得多。
2. **跨宿主红队补实现方盲区**：#2/#3/#5 是我自查漏、Codex 咬到的——印证报告 §5.4
   「异构验证」(换个模型族看同一段代码)。
3. **闭环验证是自愈系统立身之本**：可信度来自确定性校验器复跑,不来自模型自称
   「修好了」;生成器-验证器同族会共谋出假阳性。
4. **神经符号分工消灭格式崩溃**：模型出意图、宿主代码拼 DOM——把「LLM 忘闭合标签」
   从架构上消除。
5. **能用 Workflow 就别用 Agent**（报告 Q4）：我们的 ReAct 循环被夹在确定性校验器
   + 结构化工具 + 人工闸之间,模型是受约束的推理节点,不是放养自主体。简单可控 >
   智能本身。
