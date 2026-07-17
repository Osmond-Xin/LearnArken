# Day 5 会话交接（Handoff）— 2026-07-17

> **AI-generated**（Claude 实现方，session 结束前交接）。目标读者：下一个
> AI session + Yi Xin。范围：Day 5 已完成部分、合并收口清单、Day 6 启动。
> 规则源：CLAUDE.md（角色边界、红队闸、当日纪要、每日循环）与
> docs/constitution.md。**权威细节以各文档为准，勿仅凭本文摘要行动。**

## 0. 一句话状态

Day 5（带引用的 RAG 问答）**实现全部完成、⚑ 重型红队三轮收敛
CONVERGED、裁决已执行**（169 测试 + live golden 5/5 全绿，分支 `feat/day5`
@ `732c7fb`，**12 个 commit，未合并未打 tag**）。剩两个人工门（复跑数字 +
手写 journal）后即可走合并链 → `v0.5.0`。然后启动 Day 6（API 与本地 demo）。

## 1. Day 5 交付了什么（均已提交在 feat/day5）

| 交付物 | 位置 | 要点 |
| --- | --- | --- |
| `learnarken query "<问题>"` CLI | `cli.py` `_cmd_query` | 单参数=问题；退出码 0 回答 / 3 拒答 / 1 fail-closed / 2 非包；`--json` 出完整答案对象 |
| MiniMax-M3 答案 LLM | `llm/minimax.py`、`config.py` | 端点先探测后实现（OpenAI 兼容 + `base_resp` 检查；`<think>` 前缀与 ```json 围栏都剥）；`.env` 加载硬化（repo-root only、`MINIMAX_*` 白名单、https 强制——Day4 #7 教训前置） |
| 有依据回答（强制溯源） | `answer/engine.py`、`answer/models.py` | 每条引用带 **chunk ID + DMC + XPath + supporting_quote**；DMC/XPath 由系统从 chunk 元数据回填（LLM 只吐 chunk id + quote，防漂移） |
| 三门 fail-closed | `answer/engine.py` | ①测量阈值短路（不调 LLM）②LLM `is_answerable`③引用确证：id⊆检索集 **且** quote 是 chunk 逐字子串（≥12 字符、非 boilerplate）；任一红灯回占位符 "I don't know…"（严格二分，INV-4） |
| 图谱同步 + 接口③注入 | `graph/store.py`、`retrieval/__init__.py` | `index` 时 MERGE 幂等入 Neo4j（DM 节点、DM→DM dmRefs 边、DM→ICN 边）；`query` 把检索命中 DM 的图谱事实以结构化列表注入 prompt（在 spotlighting 定界符内） |
| 五跨度 answer trace | `answer/trace.py` | 每次查询落 `eval/traces/<trace_id>.json`（git-ignored）：retrieval/rerank/llm/generation/graph/outcome |
| 拒答阈值（测量产物） | `tools/measure_refusal_threshold.py` → `eval/results/day5-refusal-threshold.json` | 零误拒规则=min answerable top-1（不 round，含完整分数分布）；加载时校验非有限/越界拒（防 NaN 绕过） |
| 20 例答案质量小评估 | `tools/answer_sample_eval.py` → `eval/results/day5-answer-sample.json` | 全集分母：answerable_success 0.875 / false_refusal 0.125 / trap_refusal 1.0；**groundedness 人工复核待 Yi Xin** |
| 红队评审 | `docs/reviews/day5.md` | Part 1（Codex 11 条，REVIEW_NEEDED）+ Part 1b 收敛日志（3 轮）+ Part 2 裁决转录 |
| 决策链 | `docs/discussions/day5.md` D1–D4 | 当天全部决策留痕 |
| 流程闸产出 | `docs/research/day5-unknowns.md`、`docs/specs/day5.md` | 研（在档）→扫→SPEC（决策层转录 + Q1–Q4 已裁决 + 探测发现） |

## 2. Day 5 合并收口清单（新 session 按此执行）

1. **环境自检**：`make test`（169 全绿）、`make lint`；确认 Vespa/Neo4j 容器
   在跑（都已 127.0.0.1 绑定）、`.env` 在 repo root（含 `MINIMAX_*` +
   `NEO4J_*`）。
2. **复跑数字（铁律，Yi Xin 本人）**——若尚未做：
   ```bash
   uv run python tools/measure_refusal_threshold.py
   uv run python tools/answer_sample_eval.py
   LEARNARKEN_HEAVY_TESTS=1 uv run pytest tests/test_day5_integration.py
   ```
   我跑的基线：live golden 5/5；answerable_success 0.875。
3. **人写 journal**（Yi Xin，AI 不碰 `docs/journal/`）：`docs/journal/day5.md`
   还不存在，需手写后提交。
4. **合并链**：`feat/day5` 已直接基于 main 最新（merge-base = main HEAD
   `4357728`，`main..feat/day5` 恰为 12 个 Day 5 提交）——**无需 rebase**，
   直接 push → PR（描述 = SPEC 链接 + 验证方式）→ squash → tag `v0.5.0`。
   之后回 main 补 Progress 表 Day 5 打勾（Day 2/3/4 的惯例）。
   （已核实：与 Day 4 不同，Day 5 分支没有叠在未合并分支上。）
5. **提醒**：`feat/day3`、`feat/day4` 远程分支已合并未删，可顺手清理。

## 3. Day 5 红队 backlog（裁决入 Day 6+，勿遗忘）

- **#8** manifest 只验 chunk id 不验内容：index 先写 Vespa 再图同步+manifest，
  失败可留下「新 Vespa 文档 + 旧图谱事实 + id 匹配的 manifest」→ 加 content
  hash / index epoch，同一 epoch 同验 Vespa+graph。
- **#9** trace 含明文 payload（问题、语料、`<think>`）：全 payload 改 opt-in、
  默认 hash/snippet、脱敏、目录 0700。
- **#10** 路径假设源码布局（`config.REPO_ROOT=parents[2]`、cwd-relative trace
  dir）：site-install 会脆——改显式配置路径/包资源。
- **#11** `_sanitize` 只剥 ASCII 控制符：Unicode bidi 覆写仍能欺骗终端输出。
- **（Day 4 遗留，仍在册）** 无——Day 4 的 Neo4j 0.0.0.0 观察项已在 Day 5 #7
  一并回环化解决。

**语义 groundedness**（supporting_quote 是 entailment 必要非充分条件）已明确
裁决归 **Day 8** 对抗评估（NLI / LLM-judge），不是遗漏。

## 4. Day 6 启动（API 与本地 demo，`v0.6.0`）

**先走每日循环 step 1：研→读→扫**（CLAUDE.md 强制）：
- **研**：报告在档 `docs/gemini-deepresearch/day6-AI应用工程化深度调研.md`
  （2026-07-15 生成）——无需重跑。
- **读**：Yi Xin 读报告 + `docs/tutorials/11-compliance-observability.md`。
- **扫**：AI 写 `docs/research/day6-unknowns.md`（未知点扫描）。

**再等 SPEC 决策层**（Yi Xin 手写，AI 不代写）：`docs/specs/day6.md` 尚不存在。
execution-plan 的 Day 6 范围：
- FastAPI 端点 `POST /validate`、`POST /query`（含 OpenAPI 文档）
- Streamlit demo：上传/选样本包 → 校验报告 → 带引用问答
- `make demo` 一条命令起全套
- **证**：本地 demo 全流程走通。

**AI 提问要点**（拿到 spec 前先想）：`/query` 复用 Day 5 `answer_question`
（answer 对象已是结构化，直接 JSON 化即可）；FastAPI 是否引入=新依赖需
INV-2 上界 pin；demo 需要 Vespa+Neo4j+MiniMax 三服务在线，`make demo` 要处理
服务未起的 fail-closed 提示；这是**非重型**节点（execution-plan 无 ⚑），红队
仍走自动闸但不必 Producer→Challenger 深循环。

## 5. 环境事实（新 session 无需重建）

- **Vespa**：容器 `learnarken-vespa`，`127.0.0.1:8080/19071`，43 chunks 已喂
  （package-a+c，含 `package` 属性字段），manifest 在 `.vespa-manifest.json`
  （git-ignored）。
- **Neo4j**：容器 `learnarken-neo4j`，`127.0.0.1:7474/7687`，已同步 10 DM
  节点 + 10 边；凭证从 `.env` `NEO4J_*` 读（回退 neo4j/learnarken）。
- **本地模型**（~/.cache/huggingface，已缓存、SHA pin）：Qwen3-Embedding-8B、
  bge-m3、bge-reranker-v2-m3。机器 M5 Max/64GB。
- **`.env`**（repo root，git-ignored）：`MINIMAX_*`（M3 chat）+ `NEO4J_*`；
  模板 `.env.example`。**HF Hub 未认证警告无害**（模型已本地缓存 + revision
  pin，不发网络请求）；要消除设 `HF_TOKEN`，非必须、不改代码。
- 验证命令：`make test`、`make lint`、上面第 2 节的复跑三连。

## 6. 高价值教训（面试素材，journal 可用）

1. **「可溯源」曾是空头支票**：引用确证原本只验 id⊆检索集（指针有效），
   重型红队一击点出「合法引用≠claim 有依据」——加 supporting_quote 逐字子串
   校验才有 groundedness 机器下界。收敛遍连追三轮（空/短 quote → boilerplate
   绕过 → 非样板检查）才真正关闭。教训：红队要攻**承诺**不只是代码。
2. **探测结果必要不充分**：M3 短 probe 没触发 ```json 围栏，第一条真实 query
   就触发——防御式解析（剥 think + 剥围栏）是 Day 4「探测再实现」纪律的延续。
3. **拒答门的纵深**：玩具规模重排分数分布重叠、单门只挡 1/15 陷阱；真正拒答
   靠三门叠加（阈值+LLM+引用确证），且阈值必须测量（零误拒规则、不 round、
   拒 NaN）——安全性质要在系统层证明，不能靠单个魔法数。
