# LearnArken

**面向航空技术出版物(S1000D)的 fail-closed 受管检索问答系统:每个答案都带
chunk-ID + DMC + XPath 溯源,否则系统拒答。从零到一自建——入库闸门、
混合+知识图谱检索、带引用问答、自愈修复 Agent、对抗评估、按需真栈部署。**

[![CI](https://github.com/Osmond-Xin/LearnArken/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Osmond-Xin/LearnArken/actions/workflows/ci.yml)

*[English version (default)](README.md)*

> **本文是非权威译本。** 对外权威版本是 [README.md](README.md);两者若有出入,
> 以英文版为准。(2026-07-26 裁定 D8。)

**为什么做这个项目。** 我做它是为了求职——目标是受监管领域「受管检索」方向的
AI engineer 岗位。所以它是**写来被核查的,不是写来被欣赏的**:下面每一个基准
数字都由已提交的产物生成、并附一条可复跑的命令;散文型主张则链到代码或裁决它的
那份评审。(说准:CI 守卫的是死链、EVIDENCE.md 里打标的数字,以及每张基准表与其
源 JSON 的比对——别处手写的散文数字并不在机器守卫内,§6 说明了为什么这个残余
缺口是被写出来而不是被说没。)玩具规模的部分、没做的部分,用和成绩同样的语气标注
出来——因为在这个领域,一个夸大自己的系统正是所要防的失效模式本身。

**按你手上的时间读。**

| 你有 | 读 |
| --- | --- |
| **3 分钟** | [§1](#1-为什么这个系统必须会说我不知道) 的三段终端输出——一个包被拒收、一个答案焊死在 XPath 上、一个问题被拒答且报出门名。然后是 [§6](#6-与受管推理架构的对照) 对 Arken 七条支柱的诚实自评 |
| **15 分钟** | 加上 [§2](#2-拦截链四条泳道16-道门全部-fail-closed)(16 道门朝同一方向失效)与 [§4](#4-混合检索先讲清原理再看消融怎么判)(消融如何推翻了我自己的预期) |
| **要审计** | [docs/EVIDENCE.md](docs/EVIDENCE.md) 是 主张→产物→命令 的映射;[llms.txt](llms.txt) 是同一张图的机器版——**把你自己的 AI agent 指过去核我的数字,别听我说** |

| | |
| --- | --- |
| **交付规模** | 13 个已交付节点,`v0.1.0` → `v1.3.0`,每天配人写 SPEC、独立红队评审、人工逐条裁决 |
| **测试** | 569 条——`make test`(即 pytest)离线跑 `557 passed, 12 skipped`(CI 即此环境);本地 Vespa + Neo4j 起着时 `560 passed, 9 skipped`。两个数字都是 2026-07-28 实跑测得,不是算出来的。lint 是单独的 `make lint` |
| **证据规则** | 复现不了的数字不发布(INV-5)——[EVIDENCE.md](docs/EVIDENCE.md) 把每条主张映射到产物 + 命令 |
| **诚实边界** | 合成 S1000D-like XML(INV-1)、教学级语料规模、分布式为单机模拟——完整清单见 [docs/constitution.md](docs/constitution.md) |

> **`INV-n` 是什么。** 动手写代码之前,我先写了一部
> [项目宪法](docs/constitution.md):八条编号的**不变式**,任何一天的工作都不许违反,
> 其效力高于任何 SPEC、也高于我自己的方便。全仓库按编号引用它们——红队报告违规时
> 直接引 ID,这让"这条被破坏了"成为一个论证而不是一种看法。下文出现最多的四条:
>
> | | |
> | --- | --- |
> | **INV-1 · 数据红线** | 仓库里只能有我自造的合成 XML,或许可证明确允许再分发的第三方文件。绝不放真实客户数据。 |
> | **INV-4 · Fail-closed 拒答** | 证据不足时系统必须拒答。每个答案要么带可核验引用,要么是显式拒答——**没有第三种状态**。 |
> | **INV-5 · 可复现性** | 每个发布的数字都要有固定随机种子、版本化 golden set、可直接粘贴的复跑命令。复现不了的数字不发布。 |
> | **INV-7 · 诚实分层** | 对外主张只能声称"有代码 + 有测试 + 有可演示产物"的能力,并保持三层永不混淆:`Implemented` / `Toy-scale` / `Planned`。 |
>
> 其余四条覆盖分布式接口纪律(INV-2)、可枚举错误注入(INV-3)、
> 人类拥有的证据链(INV-6)与反漂移规则(INV-8)。

---

## 1. 为什么这个系统必须会说"我不知道"

维修工程师站在飞机旁打开电脑,**现在**就要找到正确的维修方案。在这个场景里,
一个自信的错误答案不是"更差一点的答案",而是完全另一类事故。所以设计约束和
消费级聊天机器人是反的:

> **Fail-closed** = 一级的失败模式是**停下**,不是**尽力而为**。
> 畸形数据包被拒收,而不是部分入库。证据不足就拒答,而不是含糊其辞。
> 无法确证的引用会**作废已经在流式输出的答案**。

有一处**已登记的例外**,写在这里而不是藏起来:Neo4j 不可达时,**图谱检索路**
返回空并记一条 warning,于是 `query` 降级为普通 hybrid 而非中止——这是对一条
*可选候选扩展*臂的可用性取舍;评估路径不继承它:`run_ablation` 会先查
`graph.is_up()` 并拒绝启动,所以基准行不可能在缺少它声称测试的那一路的情况下被测出来。

三段真实输出(拒收 → 回答 → 拒答),取自 2026-07-25 的一次实跑,并且是
**为版面裁剪过的摘录**:finding 用 `…` 省略、长行折行、CLI 同时打印的
HuggingFace 缓存警告被删。要看字面输出请自己跑一遍命令。

```console
$ uv run learnarken validate samples/package-b
  Findings: 7 error(s), 1 warning(s)
  [BREX-001/error] 危险步骤前无 warning/caution
  [XREF-001/error] dmRef 指向包内不存在的 DMC-LA100-A-29-20-00-00A-520A-A
  [XREF-003/error] 模块自称 issue 003-00,但 DML 登记为 001-00
  [XREF-004/error] modelIdentCode 'SS200' 不在接受集 ['LA100'] —— 错领域文档
```

注意它**不做**什么:不自动修正。每条 finding 附一行 `fix:` 供人处置——
机器负责发现,人负责裁决。

```console
$ uv run learnarken query "What safety precautions apply before removing the hydraulic pump?"
Before removing the hydraulic pump, make sure the hydraulic system pressure is
fully released before disconnecting any line, ...

  106807baae8e3f1c  DMC-LA100-A-29-10-00-00A-520A-A
                    /dmodule/content/procedure/preliminaryRqmts/reqSafety/safetyRqmts/warning
    ↳ "Hydraulic fluid under pressure can penetrate skin and cause serious injury…"
  model=MiniMax-M3 · trace=eval/traces/20260725T151139-6c281bc4.json
```

引用不是脚注,而是**指向源文档的 XPath**,外加一句必须能在被引 chunk 里
逐字找到的原文。LLM 只被允许输出 chunk id,DMC 与 XPath 由系统回填——
模型无法编造一个看起来像模像样的出处。

```console
$ uv run learnarken query "APU automatic start sequence"
I don't know — no answer was found in the indexed corpus.
  (refused · gate=llm · trace=20260725T151158-bed9b006)
```

没有第三种结局。拒答是一等公民结果:它报出是**哪道门**拦下的并写 trace,
所以误拒是可调试的而非玄学。误拒率与陷阱拒答率都是**实测**的(见 §5)——
一个什么都拒答的系统同样是坏的。

### 同样三种结局,在浏览器里

上面三段是命令行。下面是同一套行为在 demo 界面里的样子。每段录屏都是**一条完整
takes,只做了裁剪和缩放——没有剪切、没有变速、没有重排**(转换本身是
[提交在仓库里的脚本](tools/make_demo_gif.sh),跑在同样提交在仓库里的源录像上),
并且每一段都带着那次运行的 trace,所以下面的说法可以拿记录去核,而不是拿信任去换。

**答案和它的证据焊在一起。** 每一句都落到 chunk id、DMC、XPath,以及必须在被引
chunk 里逐字找到的那段原文。

![一次作答,以及它的引用表](docs/assets/demo-answer.gif)

*Trace:[`demo-answer.trace.json`](docs/assets/demo-answer.trace.json)*

**一次不花钱的拒答。** 语料里没有任何 chunk 分数越过实测阈值,所以问题在**模型
被调用之前**就被拒了——这段录屏里根本没有出现 `Generating (LLM)…` 这一步。这句话
可以核而不必信:trace 里 **`"llm_called": false`**,因为引擎在检索阈值门拒答时
根本不会写 `llm` span。拒答依然是被路由的:怎么解决、谁该处理。

![一个语料外的问题在检索阈值门被拒](docs/assets/demo-refusal.gif)

*Trace:[`demo-refusal.trace.json`](docs/assets/demo-refusal.trace.json)*

**一次撤回,以及它到底撤走了什么、没撤走什么。** 这一次模型在吐出任何答案文本
**之前**就判定证据不足,所以撤回协议触发了,但屏幕上没有任何可见内容被拿走。界面
如实这么写,而不是暗示一次观众从未看见的撤回——trace 里也带着
**`"answer_text_emitted": false`**,所以这个区分同样可核。把「协议运行了」和
「有文字被撤回」分清楚,正是 demo 最容易含糊过去的地方。

![一次撤回,以及随后的路由拒答](docs/assets/demo-retraction.gif)

*Trace:[`demo-retraction.trace.json`](docs/assets/demo-retraction.trace.json)*

录制流程、逐字查询、精确的转换命令与实测复现率见
[docs/assets/CAPTURE.md](docs/assets/CAPTURE.md)。发布出来的 trace 是**裁剪过**
的——完整提示词和模型原始输出由 [`tools/public_trace.py`](tools/public_trace.py)
去掉,那个脚本自己写明了删了什么、为什么删。

### 为什么是场景先于技术栈

做工程师之前我做产品经理,当时奉行的一条规矩是:没有去一线坐在终端用户旁边看过
之前,不许开始设计。

印象最深的一次访谈:我发现我的终端用户是调度员——初中文化程度,打字只会单指按。
我设计的每一块界面、每一条流程,都在默认使用者是一个键盘熟练的办公室白领。那套
软件不是做错了,是**对唯一会碰它的那群人不可执行**。于是界面和流程我全部推倒,
按那位用户真正能做到的动作、真正能达到的速度重建。

这就是这个仓库底下的那条信念:**一个站在问题面前的人执行不了的系统,不是系统,
是 demo。** 所以这个项目不是从技术栈开始的,是从场景开始的——飞机旁边的那位
工程师,写在 [docs/constitution.md §1](docs/constitution.md) 里,时间是 Day 1
(2026-07-12),早于任何一行代码;和它一起写下的是那个场景不容谈判的两条性质:
**延迟**与**召回**。这就是为什么检索消融表把 p50 和召回并排报、而不是只报召回
([BENCHMARKS §3](docs/BENCHMARKS.md)),也是为什么问答路径被造成宁可拒答也不
含糊其辞。§2 的那些门是这个决定的下游,不是它的起点。(既然这页是给人查的,就说
准:宪法里写的是基准"始终同时报告两者",而分块策略表与嵌入供应商表只报了召回。
是那条规矩说过头了——在此记录,而不是默默继承。)

## 2. 拦截链:四条泳道,16 道门,全部 fail-closed

真正的工程含量不在某个模型,而在于**16 道门朝同一个方向失效**:每一道的失败模式
都是 拒收/拒答/丢弃/拒绝,绝不是"少点东西接着跑"。去掉任何一道,系统就会在某个
具体位置开始一本正经地胡说。(代码里唯一那处刻意的例外——Neo4j 挂掉时可选图谱路
降级——已在 §1 点名,且不属于这 16 道。)

### 入库泳道——文档想进知识库

| # | 门 | 拦住什么 | 代码 · 测试 |
| --- | --- | --- | --- |
| 1 | **XML 加固(L0)** | XXE、实体膨胀、DTD/网络取用、畸形 XML——先由 `defusedxml` 过筛,再交给锁死的 `lxml`(`resolve_entities=False`、`no_network=True`、`load_dtd=False`) | [loader.py](src/learnarken/loader.py) · `test_validation.py` |
| 2 | **结构(L1)** | 对照项目 mini-XSD 缺失的必需元素/属性 | [validation/rules.py](src/learnarken/validation/rules.py) |
| 3 | **业务规则(L2 · BREX)** | 项目自定义违规——如危险步骤前无 warning、DMC 字段畸形 | [validation/rules.py](src/learnarken/validation/rules.py) |
| 4 | **跨文件完整性(L3)** | 悬空 `dmRef`、缺失 ICN 插图、DML issue 号不符、**错领域模块**(舰船模块混进飞机库)——均为 error 且拒收。引用环报 `warning` 不拒收:S1000D 并不禁止环,所以这道门只标记不停机 | [validation/engine.py](src/learnarken/validation/engine.py) |
| 5 | **图形绑定** | 描述与字节对不上的图像——PNG 按 SHA-256 绑定,VLM 描述出的热点与 DM 声明集**机械比对**,越出包目录的 ICN 路径拒绝 | [multimodal/ingest.py](src/learnarken/multimodal/ingest.py) |
| 6 | **语料清单** | 查一个"你以为是那样"的索引——分块策略、嵌入提供方、**锁定的模型 revision** 与 chunk-id 集必须同时匹配清单**和**引擎实际 doc id,否则中止。作用于问答与评估路径(`query`、`eval`);探索性的 `search` 命令**不**调用它 | [retrieval/\_\_init\_\_.py](src/learnarken/retrieval/__init__.py)(`verify_corpus`) |

### 问答泳道——问题想拿到答案

| # | 门 | 拦住什么 | 代码 · 测试 |
| --- | --- | --- | --- |
| 7 | **重排阈值** | 拿弱证据作答。阈值是*实测*的(`eval/results/day5-refusal-threshold.json`);若该产物缺失或不在 `[0,1]`,引擎**拒绝启动**,而不是悄悄关掉这道门 | [answer/engine.py](src/learnarken/answer/engine.py) |
| 8 | **LLM 输出契约** | 对坏响应做"尽力解析"——JSON 非法或缺键即*拒答*,不做抢救 | [answer/engine.py](src/learnarken/answer/engine.py) |
| 9 | **可答性** | 模型自报 `is_answerable: false`,按约束力执行而非二次猜测 | [answer/prompt.py](src/learnarken/answer/prompt.py) · [answer/engine.py](src/learnarken/answer/engine.py) |
| 10 | **引用 + 逐字原文** | 看着像样、背后没东西的指针。每条引用必须指向**被检索到的** chunk,**且**带一句是该 chunk 字面子串的 `supporting_quote`。失败会**回撤已流式输出的文本** | [answer/engine.py](src/learnarken/answer/engine.py) · `test_day5_answer.py` |
| 11 | **图形二次看图(G15)** | 编造图里有什么。视觉问题以**多采样共识**重读图像(不稳定 VLM 通道的单次读不可信);已核验描述支撑不了的内容在引用确证处拒答。**范围说准**:正向 grounding 逐词检查在*全部*被引 chunk 都是图形时触发,图文混合答案目前不逐词复检 | [answer/figure_relook.py](src/learnarken/answer/figure_relook.py) · [answer/engine.py](src/learnarken/answer/engine.py) |

图谱事实注入路径上的错误向上传播而非被吞掉——绝不用降级上下文顶替完整上下文。

### 修复泳道——补丁想被写盘

| # | 门 | 拦住什么 | 代码 · 测试 |
| --- | --- | --- | --- |
| 12 | **确定性复验** | LLM 给自己发合格证。补丁先写进沙箱,再由确定性校验器复跑;只有真实的 finding 前后差值才算修好,写入中途失败会还原原文件 | [repair/tools.py](src/learnarken/repair/tools.py) · `test_day7_repair.py` |
| 13 | **reward-hack 否决** | 删掉节点让告警消失——删除比例超阈值的补丁,即使复验通过也否决 | [repair/tot.py](src/learnarken/repair/tot.py) |
| 14 | **批准后写入** | 静默改动。默认 dry-run;`--apply` **逐 patch** 询问;批准集合先整体应用到临时副本复验,若引入**新** finding 则整体丢弃;换入有 journal、可崩溃恢复 | [repair/apply.py](src/learnarken/repair/apply.py) |
| 15 | **沙箱牢笼** | Agent 的代码执行工具够到文件系统或网络——AST/argv 白名单、临时目录 jail、rlimit、超时。**诚实标注**:这是应用层围栏,不是 OS 隔离,生产该跑在 nsjail/gVisor 里 | [repair/sandbox.py](src/learnarken/repair/sandbox.py) · `test_day7_sandbox.py` |

### 暴露泳道——公网 demo 想花钱

第 16 道门(一个信封、四道围栏):生成路径上的 **LLM 调用配额 + 并发上限**——模型花费不走云账单,这是唯一看得见它的围栏;所有状态变更/花钱路由上的共享 `X-Demo-Key`;**上传熔断**(上传会污染与下一位访客共享的语料);以及 VM 内按内核时钟执行的 **30 分钟闲置 + 3 小时硬顶自动关机**,外加预算告警。
([api/demo_guard.py](src/learnarken/api/demo_guard.py) · [deploy/](deploy/runbook.md))

## 3. S1000D 是什么,以及它如何决定了上面每一道门

S1000D 是航空航天/国防/船舶技术出版物的国际规范。三个性质决定了本项目的设计:

**标识符是结构化数据,不是文件名。** 数据模块(DM)是内容单位,其 **DMC** 编码了
机型、系统差异、SNS 系统/子系统/单元、拆解、信息类型与件位:

```
DMC-LA100-A-29-10-00-00A-520A-A
    │     │ │  │  │  │   │    │
    │     │ │  │  │  │   │    └── 件位码
    │     │ │  │  │  │   └─────── 信息码(520)+ 变体(A)
    │     │ │  │  │  └─────────── 拆解码(00)+ 变体(A)
    │     │ └──┴──┴────────────── SNS:系统 29 · 子/子子系统 10 · 组件 00
    │     └────────────────────── 系统差异码
    └──────────────────────────── 机型识别码
```

字段位置与语法在代码里建模并校验([models.py](src/learnarken/models.py) 的
`DmCode`、[validation/rules.py](src/learnarken/validation/rules.py))。**语义**这一层
才是诚实要紧的地方:**本仓库不提供权威的 SNS / 信息码字典**。语料能证明的是
ATA 第 29 章是液压动力,以及这里带信息码 `520` 的模块标题是
*"Hydraulic pump — Remove procedures"*——证据是标题,不是一张解码表。

这就是为什么 BM25 那一路要用**保标识符分词**(把 `LA-29-0025-7` 切碎等于毁掉查询),
为什么第 ④ 道门只看 `modelIdentCode` 就能识别错领域模块,以及为什么 golden set 里
**被扰动过的** DMC 必须返回**零命中**而不是最近邻。

**合规是可机检的,而且是项目自定义的。** **BREX**(业务规则交换)是项目用机器可读
形式声明自身规则的地方——这让第 ③ 道门是一个规则引擎,而不是一堆硬编码的主观判断。
**DML**(数据模块清单)按 issue 号登记每个模块,所以过期版本是可检测的,不是模糊的。

**语料天生是图。** 模块间 `dmRef` 交叉引用与 `graphic` 指向的 ICN 插图都在 XML 里
声明过。所以本项目的知识图谱是**把这些声明确定性地序列化进 Neo4j**得到的——
没有 LLM 实体抽取,没有幻觉边。同一张引用图同时是 L3 完整性检查、
`graph impact` 反向依赖查询,和 §4 的检索第三路。

结论:S1000D 不是"恰好带链接的文档格式",而是**带校验契约的图**。
本项目的门与 KG 路线是从标准里长出来的,不是外挂上去的。

## 4. 混合检索:先讲清原理,再看消融怎么判

真实维修查询不是一种查询:件号与 DMC 是**词法**的;"拔泵之前要做什么"是**语义**的;
"这条警告会传播到哪些模块"是**结构**的。一个检索器不可能三项都最好,所以四级并行融合:

| 级 | 机制 | 为哪类查询存在 |
| --- | --- | --- |
| **稀疏** | 保标识符分词的 BM25 | 精确件号、DMC、目录码 |
| **稠密** | 本地 Qwen3-Embedding-8B(revision 锁定)+ Vespa 精确 `nearestNeighbor` | 与手册不共享词元的改写、"怎么做…"式提问 |
| **图谱** | 确定性实体链接(regex + 语料词典,**无 LLM**)→ 1–2 跳 `REFS` 遍历,环安全、限枢纽 | 答案跨模块的多跳问题 |
| **融合** | RRF,k=60 | 三路分数**不可比**,RRF 融合的是**名次**,无需分数校准 |
| **重排** | `bge-reranker-v2-m3` 交叉编码器,20 候选 | 唯一**联合**看 query 与文档的一级 |

人工标注 golden set(82 题)实测(完整表/分类别拆解/延迟见
[docs/BENCHMARKS.md](docs/BENCHMARKS.md)):

| 模式 | Recall@5 | Recall@10 | nDCG@10 | p50 |
| --- | --- | --- | --- | --- |
| bm25 | 0.83 | 0.88 | 0.77 | <1 ms |
| dense | **0.99** | **1.00** | **0.90** | 56 ms |
| hybrid (RRF) | 0.93 | **1.00** | 0.88 | 6 ms |
| hybrid + rerank | **0.99** | 0.99 | 0.88 | 123 ms |

**这些数字描述的是它们被测量时那套 43 chunk 的语料(Day 4),不是今天的。** Day 12
给两个被评测的包都加了图形资产,语料变成 45 chunk,今天重跑同一条命令会在 32 个
指标格里有 12 个不同。这张表**原样保留、不刷新**:一个基准数字是"某个语料在某个
版本上"的陈述,原始素材一变,先前的测量就**作废**,而不是"近似仍然成立"。保留这份
带作用域的记录是裁决本身([ADR-0004](docs/adr/0004-measurements-are-bound-to-their-corpus.md))。
它同时点出了那道不存在的守卫:CI 守的是"表与产物一致",没有任何东西守"产物与语料
一致"。

**三条对我自己不利、但必须写出来的结论:**

- **教科书预期没有兑现**。"稠密检索在标识符查询上会输"是标准说法;在本语料规模下,
  8B 嵌入把它们解得很好。是消融告诉我的,不是直觉。
- **图谱路在重排之后是平的**。`hybrid+graph+rerank` 与 `hybrid+rerank` **逐位相同**:
  43 个 chunk、每路 20 候选,候选池几乎覆盖全语料,一条"负责捞回别人漏掉的 chunk"的
  路线自然无物可捞。它的实测价值是多跳问题的**重排前排序信号**(MRR 0.81→0.89)
  与引用路径可解释性。**作为机制交付,不当成基准收益兜售。**
- **任何含稠密的模式都不会拒答**:稠密恒返回 k 条,融合继承这一点,所以检索层的
  "零命中"拒答只存在于纯 BM25。拒答只能建在问答层——也就是第 ⑦–⑪ 道门。

两项候选技术**基于证据被否决**:SPLADE 与 ColBERT(它们要治的改写缺口已经闭合,
标识符查询也没有在输)——[ADR-0001](docs/adr/0001-day4b-gate-stays-shut.md);
numba、自写 Rust 扩展、Python free-threading 同理,profiler 显示本语料无靶——
[ADR-0003](docs/adr/0003-day13-rust-gate.md)。**有理有据地不做某件事,也是工程交付物。**

## 5. Golden set 与度量纪律

上面每个数字都压在**人工标注 golden set** 上,而 harness 被刻意设计成"很难顺手
产出一个好看的数字":

| 集合 | 规模 | 用途 |
| --- | --- | --- |
| `day3.jsonl` | 32(27 可答 + 5 陷阱) | 分块策略对比 |
| `day4.jsonl` | 82(67 可答 + 15 陷阱) | 检索消融——**全部行经人工复核** |
| `day8-adversarial.jsonl` | 32 | 攻击集:改写不变性 / 扰动 / 无答案 / 跨文档 |
| `day11-multihop.jsonl` | 10 | 多跳问题,按反循环协议人工出题 |

- **无答案陷阱是一等公民**:每套集合都含"正确行为是什么都不返回"的查询,包括
  **被扰动的标识符**(它们合理地夹在真标识符之间)。没有它们,"召回率"会奖励一个
  永远作答的系统。
- **反循环**:多跳题目按书面协议出题,避免从"检索器本来就能找到的东西"倒推
  ([eval/golden/README.md](eval/golden/README.md))。
- **评估器本身也要被评估**:groundedness 由**两个异构裁判**(Codex/GPT 系与
  Gemini 3.1 Pro)判定——绝不用生成器同族模型(同族会偏袒自己的幻觉)——头条取
  **交集**;裁判再用 30 条人工盲标以 **Cohen's κ** 校准(Codex 0.74、agy 0.67,
  "substantial",但刻意不到"可以盲信"的程度)。
- **非确定性是被度量的,不是被平均掉的**:生成器在 temperature 0 仍不确定,
  所以行为按 N=3 重复跑取均值;当整体指标只在噪声内移动时,README 就照实写"持平",
  而不是宣称赢了。诚实结论:一个**可复现的**跨文档算术缺陷从 3/3 消除到 0/3,
  而整体通过率 0.94 → 0.92 持平;裁判判定的 groundedness 确实动了:交集 0.53 → 0.69。
  这四行原本是手敲的,2026-07-25 的审计发现它们与自己的产物漂移了,现在已改为从冻结
  JSON **生成**——修的是漂移这一类问题,不是修一次数字
  ([BENCHMARKS §6](docs/BENCHMARKS.md#6-adversarial-evaluation--day-8))。
- **表格是生成的,不是敲出来的**:基准表由 `tools/gen_benchmark_tables.py` 从
  `eval/results/*.json` 渲染,漂移会让测试挂掉。这道守卫的由来是:曾经有一行手改的
  表格在算术上不可能成立——是红队抓到的,不是我。
- **每个数字都附命令**(INV-5)。跑不出来的,就不发布。

## 6. 与"受管推理架构"的对照

本项目**事后对照**了 Arken 公开的架构文档([thearken.com/architecture](https://thearken.com/architecture))
——七条必须**同时成立**的性质。"事后"这个词是承重的:十三份日常 SPEC 是照着本项目
自己的宪法写的,没有任何一份引用过那七条性质。下面这张表是一次事后审计,不是把
设计意图追认成当初就有的东西。诚实自评,包括够不着的地方:

| 支柱 | 本项目现状 | 层级 |
| --- | --- | --- |
| **拒答是一等公民输出** | 严格二值作答、5 道拒答门、拒答带门名返回、误拒率与陷阱拒答率实测。**部分**:入库 finding 带 `fix:` 补救建议,而**问答**拒答目前只报门名,还不会提出"怎样才能解决" | 已实现 / 部分 |
| **可溯源输出(trace)** | 每次作答在**运行中**写五段 trace:检索候选、重排分数+阈值、注入的图谱事实、确切的 LLM 请求、结局与引用(chunk ID · DMC · XPath) | 已实现 |
| **审计内建** | trace 运行中生成、绝不事后重建;[EVIDENCE.md](docs/EVIDENCE.md) 映射 主张→产物→命令;裁判判定冻结为产物。**守卫范围要说准**:CI 守卫覆盖死链、EVIDENCE.md 里打标的数字,以及每一张基准表与其源 JSON 的比对。别处手写的散文数字仍不在守卫内——之所以照实写而不是抹掉,是因为确实有一张手敲的表漂移了,2026-07-25 被红队抓到,应对方式是把它挪进生成器 | 已实现——有已点名的残余缺口 |
| **部署主权** | 本地优先:嵌入(Qwen3-8B)、重排、Vespa、Neo4j 全部**跑在本机**,索引与源语料不出机。生成端是 OpenAI 兼容的,所以本机回环模型服务(llama.cpp / vLLM / Ollama)可直接替换——并且 **`LEARNARKEN_LOCAL_ONLY=1` 是一道硬出网围栏**:armed 之后,非回环端点会直接抛错而不是被调用,chat 路径、VLM 路径、评估 harness 与 API 一视同仁([config.py](src/learnarken/config.py))。**残余缺口照直说**:本仓库不附带本地 chat/VLM 模型,所以默认配置下检索出的证据片段与图形字节**确实**会离开本机。围栏是强制力,提供本地模型是部署动作 | 可强制且已测——未附带本地模型 |
| **推理前授权** | 有包级作用域检索、共享门钥、公网模式熔断。**用他们最锋利的那句话来量这个缺口**——"*Authorization constrains reasoning, not just retrieval*"([/trust](https://thearken.com/trust)):本项目 Vespa 系检索模式是*先检索、后过滤*([retrieval/\_\_init\_\_.py](src/learnarken/retrieval/__init__.py)),正是这句话所排除的姿态。他们的五级披露与六种 RBAC 角色,这里也没有任何对应物 | 部分——已点名缺口 |
| **Gap 作为独立类别** | **机制已建,并且它撞出了边界。** `learnarken gaps` 输出一等公民 gap 对象:确定性签名(被声明的 DMC)、声明路径(`dmRef` 或 DML 登记)、以及一个被路由到的 owner 或一个显式的"未知"——绝不猜([gaps.py](src/learnarken/gaps.py))。**但他们的定义说的是"*已准入*的知识",而在本系统里"声明了却不存在"是入库错误,所以携带它的包会被拒收、从未被准入。** 两个类别相接于一个阶段边界:能交付的是 `pre_admission_declared_missing`。已准入那一类在所有准入包的并集上计算,在当前语料上**为空**——如实报空,而不是拿 pre-admission 那类去填。owner 来自项目自撰的映射,不是 S1000D 的 `responsiblePartnerCompany` | Toy-scale——机制是真的,Arken 那个情形还够不着 |
| **目标导向的知识组织** | **未实现**——而且是我最认同的一条,见下方附注。此处知识按文档结构(DM/DMC/SNS)组织,而非按组织的工作目标 | 缺口 |

三条已实现(其中一条带已点名的残余缺口)、一条部分、一条可强制但尚未完整部署、一条 Toy-scale、一条真缺口。声称七条全中,恰恰就是这套架构所要防的失效——而 gap 那一条正是个小案例:机制干干净净地建好了,然后是*定义*不肯合上,因为 fail-closed 的入库闸门恰恰会拒收那些 Arken 要去路由其 gap 的包。这个发现比这个功能更值钱,所以两者都照实报。而当这张表的初稿**确实**说过头时("语料不出机"),应对方式是去代码里找到并移除那个阻碍,而不是把句子改软:见 [F-02](docs/reviews/readme-refactor-2026-07-25.md)。

### 关于第七条,以及我的实践在哪里遇上了它的理论

目标导向这一条源自 **Goal-Oriented Knowledge Management**(Balafas, Jackson &
Dawson,Loughborough,2004)——Arken 公开表示自己建立在 GOKM 之上。**这篇 2004
年的论文我没有读过**:原文没能找到。我真正读的是同一组作者的十二步知识管理实施
方法论(Dawson,2009),GOKM 的引用正出现在它的参考文献里。把两者中我实际读了
哪一篇说清楚,和 INV-5 是同一条规矩,只不过用在了参考文献上。

读到它的时候,上面那个调度员的故事才第一次有了名字。它的 Step 7——
*让用户参与解决方案*——论据是一套国家级军方行政系统:按期、按预算、按规格
交付,却被使用者当成灾难,原因只有一个,终端用户从头到尾没被咨询过一次。(论文给
了那个项目一个金额。这里不转载:INV-5 只认"在本仓库能重跑出来的数字"或"不写
数字"——能引用出处不等于能复现它,而且这个论据不需要那个金额。)这正是
我当年做 PM 的直觉;我当年没有的,是解释**为什么**它成立、以及它还牵着什么一起
走的那套框架。

它牵着走的那部分,恰恰是我缺的。同一套方法论要求:先有一个被公认的问题(Step 1),
在动手之前**量出这个问题的成本**(Step 2),据此算投资回报(Step 4),确认对每一个
必须喂养系统的个体都有价值(Step 5),事后再实测省下了多少(Step 10)。这个仓库有
这套纪律的**工程**那一半——增量推进、每个组件单独论证、测试、评估之后才加下一个
(Step 12),被证据否掉的技术选型留在 [docs/adr/](docs/adr/)——而截至今天,
**商业那一半一条都没有**。整篇 README 里没有出现过任何一个成本基线。按我所认同
的这套理论自己的标准,这是一个真缺口;在这里点名,比在面试里被发现便宜。

所以第七条不是"设计上不同"。它是我最认同、但没有建的那一条。他们自己的表述——
"*GOKM 是围绕工作的目标构建的——正在做的那个决定、**正在执行的那道程序**、
必须站得住的那个答案*"([/whitepapers](https://thearken.com/whitepapers))——
和 S1000D 近到让人不安:正在执行的那道程序,恰恰就是一个数据模块本身。这里的知识
按 S1000D 给我的文档结构组织,而一个目标层——以*液压泵更换后放行飞机*作为组织
对象,带上它有序的数据模块、前置条件与各道门——应当叠在其之上。S1000D 的 task /
procedure 结构让这段距离比多数语料都短。没有建的原因是:真实的目标分类必须来自
真正做这项工作的组织,我自己编一套,恰恰就是上面那个 Step 7 的失败。

## 7. 怎么造出来的——规格驱动、AI 实现、对抗评审

本项目的第二个作品是交付方法本身。每天一个节点,固定七步:
**学 → 规(人写 SPEC)→ 做(AI 实现)→ 审(独立只读红队)→ 裁(人逐条裁决)→
证(验收)→ 交(tag)**。

三道装不出来的理解闸,全部留痕:

| 闸 | 证据位置 | 为什么装不出来 |
| --- | --- | --- |
| SPEC **决策层**人写(目标/验收标准/砍掉什么/关键取舍) | [docs/specs/](docs/specs/) | 拆解与判断力直接暴露在文字里;AI 起草的展开层明确标注 |
| 裁决人写 | [docs/reviews/](docs/reviews/) | 不理解实现就无法判断红队 finding 真假 |
| 日志人写 | [docs/journal/](docs/journal/) | 固定三问:学到什么 / AI 错在哪 / 我拒绝了 AI 什么 |

红队纪律:**评审模型必须与实现模型不同**、只读不写、报出的每个数字本人复跑后才合并。
有几天红队直接给了 `DO_NOT_MERGE`——那些 finding 和对应裁决都留在仓库里,没有被抹掉
([docs/redteam.md](docs/redteam.md) · [docs/AI-COLLABORATION.md](docs/AI-COLLABORATION.md))。

交付记录:13 个节点,`v0.1.0` → `v1.3.0`(骨架与宪法 → 规范模型与校验器 → BM25 基线 →
混合检索 → 带引用问答 → API 与 demo → 修复 Agent → 对抗评估 → 证据链 → 按需部署 →
KG-RAG → 多模态 → 性能实验)。逐日验收标准见
[docs/execution-plan.md](docs/execution-plan.md)。

## 8. 诚实边界

主动写在前面,不让评审者自己去发现(INV-7):

- **合成数据**:样本包是自造的 S1000D-*like* XML,附可枚举违规清单(INV-1);
  不使用、不复制任何真实 S1000D 内容。
- **玩具规模**:43–45 个 chunk。检索数字说明的是"在这里哪个设计更好",
  不是生产召回率。延迟数字来自单台开发机、热缓存、无并发——不声称任何 SLO。
- **"合规"= 本项目的校验器这么认为**:仓库里没有 S1000D 合规性的专家真值。
- **分布式是单机模拟**:接口按真分布式设计(分片在抽象之后、与串行基线逐字节等价、
  无共享内存捷径),但不存在多节点运行。
- **修复沙箱是应用层围栏**,不是 OS 隔离。
- **公网 demo 是单访客**、共享门钥、明文 HTTP;TLS 与逐收件方会话鉴权是已登记的
  切片外事项([docs/reviews/day10.md](docs/reviews/day10.md))。
- **已知欠账**,公开挂账:数字/单位感知的答案匹配(子串匹配会把 `125 Nm` 当作满足
  `25 Nm`)、裁判调用熔断、index content-hash/epoch、分级幻觉边界策略,
  以及完整 RDF/SPARQL 图谱(目前只建了确定性依赖图切片——
  [ADR-0002](docs/adr/0002-minimal-graph-query-slice.md))。

## 9. 跑起来

```bash
uv sync --locked                               # Python 3.12 + 依赖(需要 uv)
make lint && make test                         # ruff,再 pytest → 557 passed, 12 skipped(离线)
uv run learnarken inspect samples/package-a    # 查看样本包摘要
uv run learnarken validate samples/package-b   # 四层校验 findings
```

完整产品面——一个 CLI,十条命令:

| 命令 | 做什么 |
| --- | --- |
| `inspect` | 包摘要(加固的 XML 解析、JSON 输出) |
| `validate` | 四层 L0–L3 校验器 |
| `dm` · `chunk` · `search` | 查看单个数据模块 · 切分成 chunk · BM25 查询 |
| `index` | 分块、用锁定的本地模型嵌入、喂进 Vespa、同步图谱 |
| `query` | 带引用的问答——要么带出处,要么拒答,没有中间态 |
| `repair` | 针对 L0–L3 finding 的自愈修复 Agent(默认 dry-run) |
| `graph impact` | 反向依赖遍历:改这个模块会波及谁 |
| `eval retrieval` · `eval ablation` · `eval adversarial` | [BENCHMARKS](docs/BENCHMARKS.md) 背后的三套度量 harness |

外加 `make demo`——FastAPI 后端 + Streamlit 客户端,SSE 流式带回撤协议
(在流式开始**之后**才触发的拒答会撤回已经显示的内容)。

`inspect`/`validate` 离线可跑。检索、问答与修复路径(`index`、`query`、`repair`、
`make demo`)需要本地服务(Vespa + Neo4j)与仓库根目录的 `.env`,详见
[docs/local-services.md](docs/local-services.md);其中的
**local-only 无出网模式**(`LEARNARKEN_LOCAL_ONLY=1` + 回环模型服务)也在该文档里。

**按需真栈 demo**:完整栈(Vespa + Neo4j + 本地嵌入/重排模型 + 远端 LLM)对任何
免费层都太重,所以不放一份长期降级的副本,而是**按请求拉起真栈**:逐收件方 token
链接打开一个兼作导览的状态页,点 start 拉起一台停机的 GCP VM 跑与 `make demo`
完全相同的拓扑(同代码、同基准、不替换后端),随后在 §2 的费用围栏下倒计时自关。
机制、安全边界与确切命令见 [deploy/runbook.md](deploy/runbook.md)。

### 仓库导览

| 入口 | 内容 |
| --- | --- |
| [docs/BENCHMARKS.md](docs/BENCHMARKS.md) | 全部基准、golden set、诚实解读与复跑命令 |
| [docs/EVIDENCE.md](docs/EVIDENCE.md) · [llms.txt](llms.txt) | 主张→产物→命令映射,面向 AI 评审者的机器可读入口 |
| [docs/constitution.md](docs/constitution.md) | 业务场景设定 + 8 条项目不变式(最高约束) |
| [docs/architecture/](docs/architecture/README.md) | 架构快照:文件清单、数据流、配置与服务、选型、API/demo |
| [docs/specs/](docs/specs/) · [docs/reviews/](docs/reviews/) · [docs/journal/](docs/journal/) | 每日证据链:SPEC / 红队+裁决 / 学习日志 |
| [docs/discussions/](docs/discussions/) | 蒸馏的设计讨论:问题 → 选项 → 决定 → 理由 |
| [docs/adr/](docs/adr/) | 架构决策记录,含基于证据否决掉的技术 |
| [docs/research/](docs/research/README.md) · [docs/gemini-deepresearch/](docs/gemini-deepresearch/) | 每日深度调研报告 + 未知点扫描 |
| [docs/redteam.md](docs/redteam.md) · [docs/local-services.md](docs/local-services.md) | 红队 recipe;本地 Vespa/Neo4j/LLM 服务手册 |
| [samples/](samples/README.md) | 样本包说明与许可证核查 |
| [deploy/](deploy/runbook.md) | 按需 GCP 部署:VM 栈、闲置看门狗、token 触发器、runbook |
| [CLAUDE.md](CLAUDE.md) | AI 实现方的操作规则与角色边界 |

学习材料(教程、日志)是中文;所有对外产出——英文 README、宪法、证据映射与全部
基准报告——是英文。

## 10. 联系方式

**Yi Xin** — Data & AI-Application Engineer。做端到端 AI 系统:检索与 RAG 管线、
LangGraph agent,以及它们底下的后端基础设施。

| | |
| --- | --- |
| **邮箱** | [jonzy.xin@outlook.com](mailto:jonzy.xin@outlook.com) |
| **LinkedIn** | [linkedin.com/in/osmond-xin-92a736308](https://www.linkedin.com/in/osmond-xin-92a736308/) |
| **GitHub** | [github.com/Osmond-Xin](https://github.com/Osmond-Xin) |
| **作品集** | **[niagaradataanalyst.com](https://www.niagaradataanalyst.com/)** |
| **工作许可** | 加拿大 PGWP,无需雇主 sponsorship |

如果这个项目让你感兴趣,**[niagaradataanalyst.com](https://www.niagaradataanalyst.com/)**
上有其余的工作:约 20 节点的 LangGraph 求职 agent(460+ 测试)、带出处归因的
LangChain RAG 管线、以及 TypeScript/Node + PostgreSQL/TimescaleDB 上的 Go/MQTT
IIoT 后端。我正在寻找检索、agent 与受监管领域受管推理方向的 AI engineer 岗位,
也乐意把本仓库里任何一道门、任何一个基准、任何一条红队裁决逐行讲一遍。
