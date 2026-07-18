# Day 6 会话交接（Handoff）— 2026-07-17

> **AI-generated**（Claude 实现方，session 结束前交接）。目标读者：下一个
> AI session + Yi Xin。范围：Day 6 已完成部分、合并收口清单、Day 7 启动。
> 规则源：CLAUDE.md（角色边界、红队闸、当日纪要、每日循环）与
> docs/constitution.md。**权威细节以各文档为准，勿仅凭本文摘要行动。**

## 0. 一句话状态

Day 6（上传 + 有据问答 Demo：FastAPI + Streamlit）**实现全部完成、两轮红队
（跨宿主对抗 Codex + 安全评审）已裁、红队发现全部已修、架构文档已更新到 Day 6
快照**（222 测试 + 8 skip 全绿、lint 干净、端到端 live 实测过，分支 `feat/day6`，
**已提交、未合并未打 tag**）。剩两个人工门（手写 journal + 走合并链）后即可 →
`v0.6.0`。然后启动 Day 7。

## 1. Day 6 交付了什么（均已提交在 feat/day6）

| 交付物 | 位置 | 要点 |
| --- | --- | --- |
| FastAPI 后端 | `src/learnarken/api/app.py` | `/health`（四服务 fail-closed 探测）、`/upload`（信封检查→四层校验→索引，**staging 事务化 + 原子换入**）、`/query`（SSE，**召回覆盖门拒答 + 传输中断**）；路由 `def` 进线程池；bind 127.0.0.1:8100 |
| SSE 流式 + answer 字段增量抽取 | `src/learnarken/llm/minimax.py` `chat_json_stream`、`src/learnarken/answer/stream.py` | 实测 M3 支持 `stream:true`（delta 含 `<think>`、无 `[DONE]`、usage=null）；`AnswerFieldExtractor` 只吐 answer 字段、跨 delta 解转义（含代理对/孤 surrogate→U+FFFD） |
| answer 引擎 `on_event` 回调 | `src/learnarken/answer/engine.py` | status/token/retract 事件；阈值门永不 retract（没生成东西）；三门拒答仍不变 |
| Streamlit 哑客户端 | `demo/streamlit_app.py` | 零 AI 操作、只 HTTP；上传四态渲染、SSE + 召回回撤 UI；渲染全转义（无 `unsafe_allow_html`）；**测试强制不 import learnarken** |
| `make demo` 一键起停 | `Makefile`、`tools/run_demo.sh`、`tools/demo_preflight.py` | fail-closed 预检 → uvicorn 单 worker → 就绪轮询（超时非零退出）→ Streamlit；均 loopback |
| 决策链 | `docs/specs/day6.md`、`docs/discussions/day6.md` | SPEC 决策层（Yi Xin 口述转录）+ 细化层（AI 起草、待审）；D1 = SSE×fail-closed 裁决 |
| 流程闸产出 | `docs/research/day6-unknowns.md` | 研（在档）→扫→SPEC；头号发现=SSE 与 INV-4 冲突 |
| 两轮红队 + 修复日志 | `docs/reviews/day6.md` | Part 1（Codex `DO_NOT_MERGE` 3×P1 + 安全评审 1×Medium CSRF）+ 实现方修复日志；**裁决 Part 2 待 Yi Xin** |
| 架构文档 Day 6 快照 | `docs/architecture/01–05 + README` | 新增 `05-api-and-demo.md`；01–04 增量补 Day 4/5/6 |

## 2. 核心决策：SSE × fail-closed（面试级，务必记住）

未知点扫描的头号发现:**引用确证只能在完整 JSON 上跑**,先吐 token 就等于先吐
未确证内容,顶撞 INV-4。扫描曾倾向「不流式」。**Yi Xin 裁决推翻:真流式 + 事后
召回**——流式 token 显式标「未经引用确证」,生成完无有效引用即发 `retract`、前端
抹掉、落标准拒答。INV-4 约束的是**最终**结果。这是「域约束 vs 通用最佳实践」的
最佳面试案例（详见 `docs/architecture/05-api-and-demo.md §2.1`）。

## 3. 红队全部已修（10 项，Yi Xin 指示「全部都修 + 自己也 review」）

| # | 级别 | 修复 |
| --- | --- | --- |
| 1 | P1 | 上传事务化:同名 staging 目录校验+索引都过后 `os.replace` 原子换入（+启动恢复 `_recover_interrupted_swap` + `try/finally` 清 staging）；active 在成功前绝不改动 |
| 2 | P1 | Content-Length 多部解析前预检 + 读后 2 MiB 上限 |
| 3 | P1 | 传输中断已吐 token 时先发 `retract`（gate:transport）再 error |
| 4 | P2 | CSRF：`_guard_csrf` 查 Origin/Referer，server 端客户端放行、浏览器跨源 403 |
| 5 | P2 | 查询/上传并发：staging（active 只含已提交文件）+ `_corpus_lock` 覆盖换入空窗 |
| 6 | P2 | `run_demo.sh` 就绪 60s 超时非零退出，不接死后端 |
| 8 | P3 | fail-closed 分支补日志（分类保持与 CLI 字符串名一致；`EmbeddingError` 本无此类，故不改 isinstance） |
| 9 | P3 | 前端 `safe_json` 包所有 `.json()`/`json.loads`，非 JSON 响应降级不崩 |
| 10 | P3 | 确认 CI 全程 `--locked`，写进架构文档 |
| 7 | P1 | （实现中已自修:非 DMC 名绕过——scanner 零文件 no-op 曾报 ingested） |

**自审额外**:`_staged_commit` 加 `try/finally` 兜底(防意外异常泄漏 staging)。
其余(retract 不重复、think 跨 delta、swap 原子性、CSRF 放行无 Origin)逐一走查成立。

## 4. Day 6 合并收口清单（新 session 按此执行）

1. **环境自检**：`make test`（222 全绿）、`make lint`；Vespa/Neo4j 容器在跑
   （都 127.0.0.1）、`.env` 在 repo root（`MINIMAX_*` + `NEO4J_*`）。
2. **人写 journal**（Yi Xin，AI 不碰 `docs/journal/`）：`docs/journal/day6.md`
   Yi Xin 已在写；**注意工作树里 `docs/journal/` 有非 AI 改动（day6.md、
   `_template.md` 删除、`_template copy.md`）——AI 一律未提交，由 Yi Xin 自行处理。**
3. **裁决 Part 2**（Yi Xin，AI 不代写）：`docs/reviews/day6.md` Part 2 逐条
   accept/reject + rationale。修复已在代码里，但接受/否决/回退的判断是你的。
4. **可选 live demo 验收**：`make demo` → 浏览器 127.0.0.1:8501 走一遍上传 +
   问答（我已 curl 层端到端验过，含事务性重传、CSRF、超大拒）。
5. **合并链**：`feat/day6` 基于 main HEAD（merge-base = main `eb3165f`），
   **无需 rebase**；push → PR（描述 = SPEC 链接 + 验证方式）→ squash →
   tag `v0.6.0`；回 main 补 Progress 表 Day 6 打勾。
6. **提醒**：`pyproject.toml` version 仍是 `0.2.0`（历史上一直与 git tag 解耦，
   Day 3/4/5 都没动它）——沿旧惯例不在 commit 里改，tag 由合并时打。

## 5. Day 6 未关的 backlog（延续 Day 5，勿遗忘）

- **#8** manifest 只验 chunk id 不验内容 → content hash / index epoch。**Day 6
  更贴近**：上传是磁盘事务化的，但 `index_package` 内部若 Vespa 半喂成功再失败
  会留孤儿文档（下次 query 的 `verify_corpus` fail-closed 拦住——诚实但需人工
  re-index 修）。缓存化 lifespan 语料时这条必须先解。
- **#9** trace 含明文 payload → opt-in / 脱敏 / 0700。**HTTP 服务后「谁能读
  trace」成真问题**；Day 6 刻意没加 `GET /traces/{id}`，别顺手加。
- **#10** 路径假设源码布局（cwd-relative trace dir、`.vespa-manifest.json`）：
  Day 6 已用 `create_app` 的 repo-root cwd 断言 + `make demo` 从 repo root 起
  兜住，但根因（backlog #10）仍在。
- **#11** `_sanitize` 只剥 ASCII 控制符，漏 Unicode bidi。
- **语义 groundedness**（引用蕴含判定）已裁归 **Day 8** 对抗评估，非遗漏。

## 6. Day 7 启动（execution-plan 范围，先走每日循环）

**每日循环 step 1：研→读→扫**（CLAUDE.md 强制）：
- **研**：报告在档 `docs/gemini-deepresearch/`（十份 2026-07-15 全生成）——按
  Day 7 主题取对应那份，无需重跑；缺则请 Yi Xin 跑官方 DR 或用 `agy` 兜底
  （须标注「模拟」）。
- **读**：Yi Xin 读报告 + 当日教程。
- **扫**：AI 写 `docs/research/day7-unknowns.md`（未知点扫描）。

**再等 SPEC 决策层**（Yi Xin 手写，AI 不代写）：`docs/specs/day7.md` 尚不存在。
Day 7 主题见 `docs/execution-plan.md`（多跳/agent 工具方向，与 ADR-0002 划的
「多跳依赖查询留 Day 7/9」呼应）——**动手前务必先读 execution-plan 的 Day 7
条目确认范围**，本文不复述以免过时。

**AI 提问要点**（拿到 spec 前先想）：多跳会用到 `graph.facts` 已就位的接口；
新依赖需 INV-2 上界 pin；是否引入 LangChain agent/tool 抽象（Day 4 D13 定的
「框架管管道原语」原则延续）；红队闸照走。

## 7. 环境事实（新 session 无需重建）

- **Vespa**：容器 `learnarken-vespa`，`127.0.0.1:8080/19071`，**43 chunks 已喂**
  （package-a+c，baseline 已在 session 末复原），manifest 在
  `.vespa-manifest.json`（git-ignored）。
- **Neo4j**：容器 `learnarken-neo4j`，`127.0.0.1:7474/7687`，凭证从 `.env`
  `NEO4J_*` 读（回退 neo4j/learnarken）。
- **本地模型**（~/.cache/huggingface，已缓存 + SHA pin）：Qwen3-Embedding-8B、
  bge-m3、bge-reranker-v2-m3。机器 M5 Max/64GB。HF Hub 未认证警告无害。
- **Day 6 新依赖**（均带 INV-2 上界）：`fastapi`/`uvicorn`/`python-multipart`
  （主）、`streamlit`（`demo` 组）、`httpx`（`dev` 组）。`var/uploads/`
  git-ignored（demo 上传落盘 + `.staging/` 事务区）。
- 验证：`make test`、`make lint`、`make demo`。

## 8. 高价值教训（面试素材，journal 可用）

1. **知道什么时候不跟最佳实践**：SSE 是 LLM 服务化的通用最佳实践,但带引用的
   维修问答里,答案合法性取决于生成完才能跑的引用确证——先吐字=承认可能吐未确证
   内容。裁决不是「不流式」而是「流式 + 把未确证做成协议里的一等 `retract` 事件」。
   能同时讲清 SSE 机制**和**为什么明知机制仍加召回,证明取舍想过。
2. **同步栈接 ASGI 声明 `def` 不是 `async def`**:同步阻塞代码写进 `async def`
   会堵事件循环(服务级瘫痪);`def` 路由自动进线程池才是正解。知道何时不该 async
   比会写 async 更能证明理解。
3. **哑客户端 = 把保证放结构里不放约定里**:UI 零 AI 操作、测试强制不 import
   领域包;和 Day 5「引用确证在引擎层不靠 prompt 约定」同一种立场。
4. **事务性上传的真问题是磁盘 vs 引擎两套状态**:staging + 原子换入让磁盘事务化
   (旧的有效模块永不因失败的重传而丢);但引擎内部(Vespa 半喂)的事务性是另一层
   (#8 index epoch)——诚实分清「我保证了哪一半」。
5. **红队要攻承诺**:CSRF「loopback 就安全」是错觉——操作员自己的浏览器就是攻击
   载体;drive-by 站点用 CORS simple request POST 合法 DMC 就能投毒语料。Origin
   门是低成本正解,且不需改客户端/测试。
