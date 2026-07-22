# Day 13 未知点扫描 — 性能工程 + 半日玩具 ToT

> **AI-generated**（Claude 实现方，2026-07-20，步骤 1c 扫）。交叉引用：
> DR 报告 A [day13a-LLM 推理期搜索](../gemini-deepresearch/day13a-LLM%20Inference%20Search%20Research.md)、
> DR 报告 B [day13b-Python 性能与并发调研](../gemini-deepresearch/day13b-Python性能与并发调研.md)、
> [tutorials/16 性能工程](../tutorials/16-performance-engineering.md)、
> [tutorials/10 Python 工程（并发版图概念篇）](../tutorials/10-python-engineering.md)、
> [tutorials/09（生产共识：能 workflow 别 agent）](../tutorials/09-agents.md)、
> [docs/discussions/day11-13-planning.md](../discussions/day11-13-planning.md) Decision 3。
> 前置资产：INV-2 分片抽象契约、Day 4 混合检索 + eval harness、Day 4b 证据开门模式、
> Day 7 修复 agent（ReAct + 沙箱 + apply 门）、Day 8 前后对比归因 + 双裁判纪律、
> INV-5 固定种子/分母纪律。**本扫描只列张力与待裁项，不代写 SPEC 决策层。**

本日双轨（planning Decision 3）：**Track A 性能工程四层各挣一行基准** +
**Track B 半日玩具 ToT**（修复 agent 单候选 vs 3 候选 + 沙箱验证器打分）。两轨在
「候选并发生成」处接缝（T13）。定位不是从零学并发/搜索，是**把已有的正确直觉换现代
术语并配上证据**（叙事从「我避免并发」改写为「我避免共享可变状态」）。

---

## Track A · 性能工程：张力清单（A1–A7）

### A1 asyncio 的真靶点不是 embedding，是外部 API 批量调用

**盲区**：直觉会拿「批量 embedding」当 asyncio 演示，但本项目 embedding 是**本地
HuggingFace 模型**（`embedding/providers.py:_local`，Qwen3-8B 本地）——CPU/GPU 密集、
**不是网络 I/O**，拿 asyncio 解它是**选错负载类型**（DR B §0 第一失分项）。诚实的
I/O 密集批量靶点是：**多模态入库的 VLM 描述循环**（`multimodal/ingest.py`→MiniMax
API）、**Day 8 双裁判判定**（外部 CLI）、**answer 引擎的 LLM 调用**。串行 vs
`Semaphore(k)` 并发的 wall-clock 要在这些真外部调用上测。
**坑**：MiniMax 订阅制、`429 = 终止信号`（记忆 `minimax-vision-channel`），并发度
**k 的上限受此约束**——k 不能拍脑袋，要写出理由进基准表（DR B §限流三件套 / 教程
§1）。限流三件套齐活：`Semaphore(k)` + `asyncio.timeout` + 指数退避重试；用
`TaskGroup` 收口避免孤儿任务吞异常。

### A2 multiprocessing 扩展曲线需要「够多的分片」才测得出拐点

**盲区**：`validation/engine.py:analyze_package` 是 lxml **CPU 密集**解析、天然 mp
靶点，也正好落实 INV-2（分片藏抽象后、幂等写）。但现语料只有 **package-a/b/c 三个
包**，1/2/4/8 worker 的扩展曲线**至少要 ≥8 个独立分片**才有意义。
**解法（待 SPEC 裁分片粒度）**：(a) 合成复制 N 份包（INV-1 合成红线不破，本就是合成
数据）；(b) 降到 **DM 文件粒度**分片（一个包内多个 `.xml`，`analyze_package` 已按
文件迭代）。**铁律**：worker 收到的是**分片描述（路径 / ID 区间），不是解析后的
`etree`**（DR B §多进程铁律），否则 pickle 序列化抵消并行收益（失败模式：小任务负
加速）。macOS 默认 **spawn 非 fork**、启动更贵 + `if __name__ == "__main__"` 守卫
陷阱 + Docker CPU 配额让 `os.cpu_count()` 撒谎——这三条要在拐点分析里认账。

### A3 profile→numba 的靶点必须 py-spy 实测，且很可能「numba 挂不上」

**盲区**：教程/DR 都警告**猜热点命中率低**（Day 4「dense 输标识符实测没输」同构）。
本项目 py-spy 实测的真热点大概率落在 **lxml 的 C 扩展内部**（`--native` 才看得到）
或**本地 embedding 前向**——**两者都不是纯 Python 数值循环，numba 装不上**（限制
清单 #3：numba 只吃数值循环）。**诚实预期**：可能找不到一个「天然的纯 Python 数值
热点」给 numba 表演。若为演示构造一个（如 RRF 融合打分、cosine 打分循环、BM25 打分
的 Python 段），必须**标注「为演示构造，非端到端瓶颈」**，收益小如实报小（Day 4b
纪律）。三列对比：纯 Python / numpy 向量化 / numba，很多时候结论是 **numpy 已吃完肉、
numba 只多挤 1.1–1.3×**——如实写比伪造 10× 更能证明成熟度。

### A4 numba 的静默回退 + 预热惩罚是计时陷阱

**盲区**：`@njit` 必须 `nopython=True`（失败**报错**而非静默退化到对象模式，DR B
§Numba 陷阱）；`cache=True` 固化机器码；**首调用 LLVM 编译延迟必须预热一次再计时**
（INV-5 计时纪律，否则把编译时间算进「优化后」是假数字）。字符串/字典逻辑 numba 无效
——tokenize 这类不能上（限制 #3），只有 numpy 数值段能上。

### A5 Rust/PyO3 = 证据开门（仿 Day 4b），大概率不开门

**盲区**：**先认账**——本栈**已在用 Rust** 的是 `pydantic-core`（规范模型校验/序列化）
与 HuggingFace `tokenizers`（嵌入/重排分词）；**注意本项目边界**：BM25 是纯 Python
rank-bm25（Tantivy 是被否候选）、向量库是 Vespa（C++/Java），都**不是** Rust。
「通过选型获得 Rust 性能」是正当工程姿态（知情消费者，DR B
§姿态定调）。**开门条件**：py-spy 证明瓶颈越过数值运算、深陷 Python 侧字符串变换/
图游走且对象分配到硬件上限。**玩具语料大概率开不了门 → 写留痕结论**（「何时不用
Rust」本身是面试资产，延续 Day 4b）。**坑**：别为凑满四层就硬写一个 PyO3 玩具——
不开门的诚实留痕比硬造的玩具更值钱。

### A6 基准数字的分母纪律（最易造假的一层）

**盲区**：每个 wall-clock 必须带**数据规模分母 + 冷热缓存状态 + 重复次数 + 固定
seed**（INV-5）；**报分布不报单点**（wall-clock 受机器背景负载抖动，多次取中位/分位，
记忆 `honest-nondeterministic-eval` / `verify-real-signal-before-acting`）。「快 N 倍」
无分母 = INV-5 事故，红队直接打回（DR B 失败模式 6）。峰值加速比不如**拐点分析**有
面试价值（「4→8 worker 只涨 1.2× 因为序列化占比升到 40%」是工程师的语言）。

### A7 free-threading 是叙事资产，不是本项目动作

**盲区**：3.13t/3.14t（PEP 703/779）是**独立构建**（cp313t/cp314t wheel），生态未齐、
基线 **3.12 不动**（DR B §独立构建 / 限制 #5）。SPEC **不承诺切换**。面试口径：「跟踪
不抢跑；GIL 移除后内置容器的隐式原子性消失、竞态风险回归，**share-nothing 反而更
值钱**」——把「新特性」聊成「判断力」（PEP 734 子解释器同理，知道即可）。

---

## Track B · 半日玩具 ToT：张力清单（B1–B6）

### B1 单候选 → 3 候选的温度陷阱

**盲区**：现 `repair/agent.py:136` 用 `temperature=0.0`。DR A 坑一明确：**temp=0 重复
请求 3 次 = 3 个字节级相同 patch，白烧 token**。3 候选必须 **temp 0.5–0.7** 或**异构
system prompt**（DR A §7.3 三人格：激进重构者 / 保守修改者 / 极简补全者）实现多样性
采样；模型高置信时即便 temp>0 仍可能雷同 → presence/frequency penalty 兜底。**单候选
基线仍 temp=0**（取最高对数概率稳妥解）。

### B2 验证器 = dry-run 沙箱（完美 ORM），在线闭环绝不引入 LLM 裁判

**盲区**：`repair/sandbox.py` dry-run 复跑校验器 = **完美 ORM / 工程世界模型**（DR A
§3.3 / §4.3）：把裁判从概率性 LLM 剥离给确定性工具，rollout 评估零误差。**best-of-n
+ 确定性 verifier = ToT 最小可用形态**（深度 1、宽度 N，DR A §4.1）。**在线打分绝不用
LLM 裁判**（位置/长度/迎合偏差，DR A §4.3）——双异构裁判 + κ 是**离线评测**手段，不
进在线闭环。全部复用 Day 7，无需新造世界模型。

### B3 FSR 是复合布尔 + reward hacking 防御要复用 Day 7 守卫

**盲区**：修复成功率**不是「沙箱不报错」**，是复合布尔：**修好目标违规 且 不引入新
违规**（DR A §7.1）。reward hacking 防御（DR A 坑二）：patch 删除 >X% 原文本 / 清空
关键数据区 → **一票否决**，无论沙箱分多高。这与 Day 7 已有的「高危类只显示不应用」
守卫（`repair/core.py:83`）、apply 门是**同源纪律**——复用不新造。可选加一层
Constitutional 批评（数据无损 / 可追踪 `<!-- AI-FIXME -->` / 最小权限 XPath 范围，
DR A §6.2）。

### B4 成本两列如实报 + 漏斗降级叙事

**盲区**：token 计数必须分 **prompt / completion**：3 候选 completion 是 **3×**，
prompt 可因缓存只算 1 次（DR A §7.1）。报**「修复成功率 × token 成本」两列**（planning
Decision 3），配**漏斗降级**（先单候选，失败才激活 3 候选，DR A 坑三/§Q5）。**别只报
成功率不报成本**——「为 20% 长尾让 100% 流量付 3× 成本值不值」是产品经理会问的边际
ROI 质询，**「何时不值得上搜索」的实测答案本身就是面试资产**。

### B5 ToT 是非确定生成器：重复测、报稳健不报噪声均值

**盲区**：延续记忆 `honest-nondeterministic-eval` + `verify-real-signal-before-acting`。
样本集 = **package-b 违规清单**（DR A §7.2 建议 50–100，玩具规模现实是个位数）→
**n<3 的类目斜体标「指示性」、报 k/n 不报百分比**（Day 4/Day 8 惯例，防「33% 提升」
小样本幻觉）。固定 seed + 记录轨迹可复现（DR A §7.3）。格式损耗（patch XML 未闭合）
被误判为「推理能力不足」会掩盖真实失败分布（DR A 坑五）→ 结构化输出剥离格式控制，
把评估焦点收在逻辑上。

### B6 候选生成并发化 = 两轨接缝，别当两件事

**盲区**：3 候选用**本日 asyncio 并发生成**（`TaskGroup` + `Semaphore`），wall-clock
与串行对比顺带进 A1 那一行基准（planning：两主题自然衔接）。理想网络下并发 3 个 ≈
串行 1 个的延迟，但吞吐压力 3×——这正是 A1 限流 k 的现实约束（B 轨复用 A 轨的
Semaphore 结论）。

---

## 必须吃透的点（must-master）

**性能工程**

1. **负载类型 → 工具映射**（脱稿画表，DR B §0 / 教程 §0）：I/O=asyncio（单线程无
   竞态）、CPU=multiprocessing（进程隔离无共享）、数值热点=numpy→numba、最后 Rust。
   **选错负载类型是第一失分**（拿 asyncio 解 CPU、拿 numba 解字符串）。
2. **GIL 原理 + 2025–26 现状**：引用计数 → 大锁 → 线程对 CPU 任务零加速、对 I/O 仍
   有效（阻塞前释放 GIL）；PEP 703/779（3.13 实验→3.14 官方支持）、独立构建 cp313t、
   PEP 734 子解释器；**移除后竞态回归 → share-nothing 更值钱**。核心叙事：「我避免的
   是共享可变状态，不是并发」。
3. **asyncio 三考点**：`await` 点交错的 check-then-act 逻辑竞态（缓存重复 fetch）、
   结构化并发 `TaskGroup`/`asyncio.timeout`（消灭孤儿任务，堪比消灭 goto）、限流三件套
   `Semaphore`+超时+退避；**红线**：事件循环内任何阻塞调用冻结全部协程 → `run_in_executor`。
4. **multiprocessing 成本模型**：Amdahl 串行段 + pickle 序列化 + 启动开销 = 拐点（约
   逻辑核 70% 处）；`chunksize` 启发式 `divmod(n, workers*4)`；「传分片描述不传数据」；
   **拐点分析比峰值加速比更有面试价值**。
5. **profile 纪律**：py-spy（采样、火焰图、`--native` 穿透 C 扩展）vs cProfile（确定性、
   观察者偏差、free-threaded 下易挂起）；先测后优、同 profile 复跑、收益带分母。
6. **编译顺序纪律**：numpy → numba → Cython → Rust，每步先问上一步够不够；numba
   `@njit(nopython, cache=True)` + 预热；**「numpy 已吃完肉、numba 只多 1.1–1.3×」如实
   报比伪造 10× 更成熟**（诚实评估纪律又一应验）。

**推理期搜索 / ToT**

7. **谱系四段**（脱稿）：ReAct（单链表/2022，克服静态推理幻觉）→ ToT（多叉树/2023，
   Game24 4%→74%，DFS/BFS + 剪枝 + 回溯）→ GoT（DAG/2023，路径合并 = 动规重叠子问题）
   → LATS（MCTS/2023，UCT 平衡探索利用，HumanEval 92.7%，≈AlphaGo 自然语言版）。每个
   给数据结构 + 传统算法类比 + 相对前作突破。
8. **何时值得搜索的双条件**：单路径易死胡同 **且** 有廉价确定性验证器（数学证明/竞赛
   编程/XML 修复正是）；反例：有真值线性任务（写 while 重试更优雅）、纯 LLM 裁判无地面
   真相 → 「幻觉的狂欢」。2025–26 共识「能 workflow 别 agent」、o1 式内化搜索。
9. **BoN = ToT 最小可用形态**：深度 1 宽度 N；成功率 `1-(1-p)^N`；**验证器够强则加宽
   比加深性价比高**得多。
10. **世界模型三形态**：仿真环境 / 规则引擎（最推崇，数学真实、零幻觉）/ LLM 模拟器
    （贵且漂移）；**dry-run 沙箱 = 工程世界模型**——把「既当运动员又当裁判」的 LLM 自评
    换成确定性 ground truth。
11. **ORM vs PRM**：ORM（结果/稀疏/客观无幻觉）vs PRM（过程/密集/易 reward hacking）；
    **在线闭环弃 LLM 裁判**（三偏差）；reward hacking + Constitutional 批评（数据无损/
    可追踪/最小权限硬规约）。
12. **反事实两用**（DR A §5）：前向（规划期多分支平行比较「哪种修复副作用最小」）、
    后向（复盘期 patch diff 拆解、控制变量定位哪段改动破坏约束）——**Day 8 缺陷消除前后
    对比就是同款后向反事实**。

---

## 盲区四象限（Anthropic "Finding Your Unknowns"）

- **知道自己知道**：share-nothing 直觉（Yi Xin 本人 Java 时代经历）、INV-2 分片抽象
  （已设计）、Day 7 沙箱 = ORM/世界模型、Day 7 apply 门 = reward hacking 防御、Day 8
  前后对比 = 反事实归因、全程红队 = 对抗自我质检、固定 seed/分母纪律（INV-5, Day 4b）。
  **全部直接复用**，本日主要是「换术语 + 补基准数字」。

- **知道自己不知道**（靠实测回答）：py-spy 实测的**真热点在哪**（A3）；asyncio 并发度
  **k 的实际上限**（MiniMax 429 触发点，A1）；mp 扩展曲线**拐点落在几 worker**（A2）；
  numba 对本项目数值段的**真实收益**（大概率小，A3）；3 候选相对单候选的**真实成功率
  增益 × token 成本两列**（B4）。

- **不知道自己知道**（旧经验直接迁移）：**nginx epoll 运维经验 = asyncio 事件循环模型**；
  **队列/无状态/幂等架构 = 正统 share-nothing + 消息传递**（不是绕开并发，是提前三十年
  用对模型）；**存储过程下推 = 热点用编译解不用并发解**；**Day 7 工具契约「宽进严出」
  = ToT 候选的结构化输出纪律**（schema 即接口）。

- **不知道自己不知道**（红队重点）：
  - **性能基准的机器噪声**——背景负载让 wall-clock 不可复现，必须多次取分布 + 记录机器
    状态（A6）；
  - **mp 平台陷阱**——macOS spawn 比 fork 贵、`__main__` 守卫、Docker CPU 配额让
    `os.cpu_count()` 撒谎（A2）；
  - **新依赖的线程/GIL 交互**——numba/渲染库与本地 embedding 模型同进程时的行为；
  - **ToT 候选同质化**——即便 temp>0，模型高置信时仍雷同（B1）；**验证器被 patch 骗过**
    ——沙箱不报错但业务逻辑被摧毁（B3）；**格式损耗掩盖真实失败分布**（B5）；
  - **边际成本陷阱**——为 20% 长尾让 100% 流量付 3× 成本，漏斗降级是唯一答案（B4）。

---

## 待 SPEC 决策层裁定（供 Yi Xin，可「给信息我转录」）

1. **mp 分片粒度**（A2）：合成复制 N 份包 vs DM 文件粒度？目标 worker 档位 1/2/4/8 是否
   需要先造够 ≥8 分片。
2. **numba 靶点**（A3）：接受「实测可能挂不上、为演示构造并标注」的诚实口径，还是只在
   py-spy 找到真数值热点时才做（找不到就写留痕）？
3. **Rust/PyO3 开门判据**（A5）：确认仿 Day 4b「profile 不达标即写留痕结论、不硬造玩具」。
4. **ToT 多样性机制**（B1）：温度 0.5–0.7 vs 异构三人格 system prompt vs 两者叠加。
5. **ToT 样本量与报数**（B5）：package-b 违规清单全量？n<3 类目「指示性」+ k/n 报分确认。
6. **本日范围边界**：GoT/MCTS/world-model 全量维持「概念掌握 + 适用边界」第二档口径
   （不实现），只落 BoN 玩具——确认。
7. **目标 tag** `v1.3.0`（planning Decision 3）。
