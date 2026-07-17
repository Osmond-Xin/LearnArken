# Day 6 未知点扫描 — API 与本地 demo

> **AI-generated**（Claude 实现方，2026-07-17，研→读→扫 第三步）。交叉引用：
> `docs/gemini-deepresearch/day6-AI应用工程化深度调研.md`（官方 DR 报告，
> 2026-07-15 生成）、tutorials/11-compliance-observability.md（选读审计节）、
> tutorials/10（结构化日志/OTel）、tutorials/05 §5（answer trace）。按 Anthropic
> "Finding Your Unknowns" 四象限做盲区扫描。**本文不含决策**——SPEC 决策层待
> Yi Xin 手写（`docs/specs/day6.md` 尚不存在）。

## 象限扫描

### 已知的已知（今天要动手的）

- **契约式端点**：`POST /validate`、`POST /query` 用 Pydantic 定义请求/响应，
  FastAPI 自动出 OpenAPI（报告 §2）。我们运气好——`AnswerResult`
  （`answer/models.py`）和 `ValidationReport.to_dict()` 已经是结构化产物，
  响应模型基本是把现有对象抬成 API 契约，不是新建模型。
- **Streamlit 只做哑终端**（报告 §3 + 陷阱三"逻辑漂移"）：UI 里绝不 import
  `learnarken.answer`，一律 HTTP 打本地 FastAPI。多轮对话历史进
  `st.session_state`（Streamlit 每次交互全量重跑脚本）。
- **`make demo` 一键起全套**：当前 Makefile 只有 `test`/`lint`/`fmt`，需要新
  target；报告 §3 给了 `backend & sleep 2 && frontend` 的模板。
- **密钥隔离**：`.env` 已 git-ignored、`.env.example` 已在、Day 5 已把加载硬化
  到 repo-root + `MINIMAX_*` 白名单 + https 强制。这一节我们**已经领先报告**。

### 已知的未知（动手前要定 / 要探测）

1. **流式响应与 fail-closed 是正面冲突的**（本次扫描的头号发现）。报告 §2
   把 SSE 流式当作 LLM 服务化的核心最佳实践（TTFB < 1s）。但我们的第三道门
   ——引用确证（quote 必须是 chunk 逐字子串）——**只能在拿到完整 JSON 之后
   跑**。一旦逐 token 往前端推，用户就会先看到未经确证的文本，之后我们才有
   机会判定"其实该拒答"——这直接违反 INV-4（严格二分：有依据的回答 xor 拒答）。
   三个出路，代价各不同，**需要 SPEC 决策层裁**：
   (a) Day 6 不做流式，`/query` 就是普通 JSON 响应（诚实、零风险、TTFB 差）；
   (b) 流式只推"进度事件"（检索中/重排中/生成中），答案本身确证后一次性推；
   (c) 真 token 流式 + 事后撤回（前端已显示的字要抹掉）——在维修域不可接受。
   我的读法：报告的最佳实践面向的是通用聊天应用，**我们的域把它证伪了**，
   这本身是面试素材（"什么时候不该跟最佳实践"）。
2. **同步栈碰上异步框架**。`answer_question()` 是**同步**函数
   （`engine.py:93`），底下 `urllib`（`llm/minimax.py`）、
   sentence-transformers、reranker 全是同步阻塞。报告陷阱五警告"async def 路由
   里用同步阻塞代码会堵死事件循环"——**正确解法不是把全栈改异步**（那是几天的
   重构，且不在 Day 6 范围），而是路由声明成 `def` 而非 `async def`，让
   Starlette 自动扔进线程池。这个选择要写进 SPEC 并留注释，否则后人会"顺手改成
   async"从而引入报告说的那个瘫痪。
3. **每请求重新分块的代价**。`answer_question()` 每次调用都
   `chunk_package()` + `_dedupe_chunks()` + `verify_corpus()` 读盘重算
   （`engine.py:110-115`）。CLI 一次性进程无所谓，**服务端这是每请求开销**。
   报告 §1"状态管理：独占式→共享式"那一行在我们这儿的具体兑现就是它：
   语料/模型该在 lifespan startup 加载一次并缓存。但缓存与 `verify_corpus` 的
   fail-closed 语义有张力（缓存了就不再检测索引漂移）——**缓存失效策略要定**
   （每请求验、启动验一次、还是按 manifest hash 验）。这条和红队 backlog #8
   （manifest 只验 id 不验内容 → content hash / index epoch）是同一个洞，
   Day 6 是顺手一起关的自然时机。
4. **本地模型 × 多 worker = 内存炸**。Qwen3-Embedding-8B + reranker 在进程内
   常驻。`uvicorn --reload` 或 `--workers N` 会**每个 worker 各加载一份**。
   demo 用单 worker 是对的，但要显式定并写进 SPEC 理由，不能默认踩。
5. **新依赖的 INV-2 上界**：fastapi、uvicorn、streamlit、httpx（或 requests）
   都要带上界 pin（Day 4 红队 #13 的先例：六个依赖无上界入库被抓）。
   已核实 FastAPI 最新 0.139.2。
6. **`make demo` 的 fail-closed 预检**（报告 §3 原则 3）：demo 依赖 Vespa +
   Neo4j + MiniMax 三个外部服务。任一没起，正确行为是**终端给明确指引**，
   不是甩 Python 堆栈，更不是静默降级。降级尤其危险——Day 4 已经立过规矩
   （"fail-closed on Vespa/embedding errors — no silent bm25 downgrade"）。

### 未知的已知（容易带错旧直觉的）

- **"加个 API 就是把 CLI 包一层"**——错在状态。CLI 的 `answer_question` 独占
  进程、读盘、退出；HTTP 是无状态共享的，语料缓存、模型驻留、并发安全全是新
  问题（报告 §1 表第一行）。这不是包装，是重构资源生命周期。
- **传统程序员的"接口先跑通再说安全"**——报告 §5 的账单视角在这里其实**不适用**
  ：我们的 demo 只 bind 127.0.0.1（Vespa/Neo4j 已是这个规矩），不上公网，
  所以 rate limiting / JWT / 预算熔断在 Day 6 是**过度工程**。报告默认"部署到
  公网"，我们不是。但输入长度上界（Pydantic `max_length`）成本近乎零、且挡的是
  本地也会犯的错（超长输入撑爆上下文窗口），值得留。**这条要 SPEC 拍板范围。**
- **trace 已经有了，别再造一套日志**。教程 11 §2 的关键设计是"trace 是审计日志
  的子集，一次落库两处受益"。Day 5 的五跨度 answer trace 就是这个单元；Day 6
  该做的是**把 request_id 和 trace_id 接起来**（报告 §4 的 contextvars 那套），
  不是并行搞第二套记录。
- **Streamlit 的"变量为什么没了"**：全量重跑模型，普通变量每次交互都重置——
  老 Web 直觉（服务端会话）在这儿失效，必须 `st.session_state`（报告 §3 + 面试
  第 4 题）。

### 未知的未知（预埋观测点）

- **trace 目录是 cwd 相对的**（`trace.py:17` `TRACE_DIR = Path("eval/traces")`）。
  CLI 在 repo root 跑，路径没暴露问题；**uvicorn 的工作目录未必是 repo root**，
  一旦服务从别处启动，trace 会散落到意外位置或写失败。这正是红队 backlog #10
  （路径假设源码布局）第一次会真正咬人的场合——Day 6 会自然触发它。
- **观测数据本身是泄密面**（教程 11 失败模式 5 + 红队 backlog #9：trace 含明文
  payload）。CLI 时代 trace 只有本人可读；一旦有了 HTTP 服务，"谁能读 trace"
  就成了真问题。Day 6 不必解决，但别扩大——比如不要顺手加一个
  `GET /traces/{id}` 端点。
- **多请求并发写 trace / 争抢模型**：demo 单人使用，但 Streamlit 的重跑模型可能
  意外并发触发请求。先埋观测（trace 里已有 trace_id），异常再查。
- **报告 §6 的 LiteLLM / Langfuse / OTel 全栈**：对 Day 6 是明确超范围，但值得
  记一笔——真要接，接入点是 `llm/minimax.py` 那一层（报告 §6 的"AI 网关抹平
  供应商差异"论点，正是 Day 4 把 MiniMax embedding 换成 Qwen3 本地时吃过的苦）。

## 必须吃透的点（面试级）

1. **为什么我们的 `/query` 不流式**——这是"域约束压倒通用最佳实践"的最佳案例。
   SSE 把首字延迟压到 1s 内的前提是"先吐出来的字不会被收回"。而带引用的维修
   问答里，答案的合法性取决于**生成完之后**才能跑的引用确证；先吐字就等于承认
   "可能吐出未经确证的内容"。在维修域，晚 3 秒 ≪ 说错一个扭矩值。答这题要能
   同时讲清 SSE 的机制（text/event-stream、`data: ...\n\n`、`[DONE]`）**和**
   我们为什么明知机制还是不用——证明取舍是想过的，不是不会。
2. **同步栈接入 ASGI 的正确姿势**：FastAPI 的 `def` 路由自动进线程池，
   `async def` 路由独占事件循环。手里是同步阻塞代码时，声明成 `def` 才是对的；
   写成 `async def` 再调同步库，是报告陷阱五那个"服务级瘫痪"。**知道什么时候
   不该 async，比会写 async 更能证明理解。**
3. **状态管理是 CLI→服务化的真正鸿沟**（报告 §1）：能具体说出我们的那条——
   `answer_question` 每请求重新 chunk 整个语料 —— 比背"要用 Redis 存会话"有
   说服力得多。并且要能接上下半句：缓存了就得回答"索引漂移了怎么办"，
   于是引出 index epoch / content hash（红队 #8）。
4. **逻辑漂移与哑终端**（报告 §3 警告 + 陷阱三）：Streamlit 里写业务逻辑 ⇒
   前后端两套规则、结果不一致。架构立场一句话：**demo 是没有业务知识的哑终端，
   所有实质计算走 HTTP 打 FastAPI。** 这条和教程 11 §4 的"权限过滤必须在检索层、
   决不靠 prompt"是同一种立场——把保证放在结构里，不放在约定里。
5. **request_id ↔ trace_id 的贯穿**（报告 §4 + 教程 11 §2）：并发下文本日志会
   交织，contextvars 在协程切换时安全（thread-local 不安全）。我们的加分点是
   已有 answer trace 这个审计单元，只需把 HTTP 层的 request_id 绑进去，
   就能"从一条 HTTP 请求下钻到检索/重排/LLM 五跨度"——教程 11 面试第 4 题
   （事故调查走查）的现成答案。
