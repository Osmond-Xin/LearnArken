# Day 12 会话交接（Handoff）— 2026-07-20

> **AI-generated**（Claude 实现方，session 结束前交接）。目标读者：下一个 AI
> session + Yi Xin。范围：Day 12 已完成部分、Day 13 启动。规则源：CLAUDE.md 与
> docs/constitution.md。**权威细节以各文档为准,勿仅凭本文摘要行动。**

## 0. 一句话状态

Day 12（多模态入库与问答 / describe-then-index + G15 二次看图）**已完整收口**：
spec 转录 + 实现 + **两轮**跨宿主红队全修 + 人裁决 + 三类评估 + journal（Yi Xin
手写）+ 提交打 tag + **已 push origin**。commit `dd210e3`,`main` 已 ff 合并、tag
**`v1.2.0`** 已打并 push。**404 测试 + 9 skip 全绿,lint 干净,工作树干净,`main`
与 origin 同步。** `feat/day13` 分支**尚未开**——下个 session 从 main HEAD 开出。

## 1. Day 12 交付了什么

| 交付物 | 位置 | 要点 |
| --- | --- | --- |
| VLM 描述客户端 | `src/learnarken/multimodal/vlm.py` | 复用 MiniMax 代理传输,多模态 `image_url`;**两条 fail-closed 停止条件**:flaky 空响应有界重试、订阅 `429` 终止;schema 约束、enum-closed hotspot |
| 合成 ICN 资产 | `src/learnarken/multimodal/figures.py` + `samples/*/icn/` | 声明式 FigureSpec → SVG + PNG(**Pillow**,非 cairosvg,见记忆 minimax-vision-channel);2 张图(pump/battery),SVG+PNG+`.describe.json` 均已提交 |
| describe-then-index 离线管线 | `src/learnarken/multimodal/ingest.py` | 渲染→SHA-256→VLM 描述→机械 hotspot diff→OCR 锚点互验→FigureRecord;**索引期复验**(sha + 声明映射,红队 R2-P1b:改 label/part 即换 chunk_id);索引文本**只用声明数据**,VLM 自由文本不入库 |
| 统一语料构建器 | `src/learnarken/retrieval/__init__.py` `corpus_chunks` | 红队 R1-P1:文本 + 图 chunk 同一构建器,index/query/verify/ablation/eval 全走它,否则图 chunk 在引擎里"foreign"→查询 fail-closed |
| G15 视觉拒答 + 二次看图 | `src/learnarken/answer/{engine,figure_relook}.py` + `multimodal/second_look.py` | 图问题超纲→G15 拒答;二次看图=**多采样共识读**(单次不可信);**自由文本幻觉 grounding 门**(见 §2.5) |
| 图引用 | `engine._figure_ref` | `[ICN-…, Hotspot NN]`;多 hotspot quote 不猜(R2-P2) |
| 三类黄金集 + 评估 | `eval/golden/day12-multimodal.jsonl`(+worksheet)、`tools/day12_eval.py`、`eval/results/day12-multimodal.json` | 三类:图中有答案 / 图中无答案陷阱(G15) / 文图冲突;**k/n 报分**;Yi Xin CONFIRMED 标注 |
| T5 分辨率/共识标定 | `tools/day12_resolution.py`、`eval/results/day12-resolution.json` | scale 最低测得=2、渲染用 3(余量)、共识 K=2;INV-5 有出处 |
| 决策链 | `docs/specs/day12.md`、`docs/discussions/day12.md` | 决策层"Yi Xin 给信息、我总结转录"(每项标出处 HUMAN/AI);讨论备忘已产出 |
| 红队 + 裁决 | `docs/reviews/day12.md` | Part1(R1)+Part1b(R2 DO_NOT_MERGE)+Part2(Yi Xin 转录裁决) |
| 诚实记录 | `docs/notes/day12-figure-noise.md`、`day12-hallucination-boundary.md` | 回归诚实报;幻觉边界议题(见 §5.3) |
| 人写 | `docs/journal/day12.md` | AI 不碰(INV-6) |

## 2. 核心设计（面试级,务必记住）

1. **不稳定生成器:单次读不可信 → 多采样共识**（Yi Xin 纠正,记忆
   `verify-real-signal-before-acting`）:MiniMax 读图会间歇返空/掉字。二次看图
   做多次独立调用→字段级共识+确定性锚点(声明 hotspot 集/零件号)互验→只在
   收敛且被佐证时接受,发散/429 一律 G15 拒答。是 Day8 评估纪律搬到**推理期**。
2. **图入统一语料是功能前提,不是可选**:图 chunk 若只进 Vespa 不进查询侧本地
   语料,verify_corpus 会判 foreign→查询 fail-closed。`corpus_chunks` 一处构建
   给所有链路,是红队 R1 最重要的一条。
3. **SHA-256 + 声明映射绑定要"强制执行"不只"存储"**:算了 sha 存进记录没用,
   **索引期要重算并比对**;chunk_id 绑定 sha+声明映射摘要,改任何 label/part 即
   换 id→旧 Vespa 文档过不了 verify(红队两轮都咬这条)。
4. **诚实的冲突处理是涌现**:系统**不检测**语义图文冲突(Decision 3b),但
   grounded QA 要求每句带引用,面对两个冲突来源会**同时引用两方**而非择一——
   冲突陷阱因此过关。非调优、是引用纪律的副产品。
5. **自由文本幻觉必须在引用确证处堵**(Yi Xin 纠正,记忆
   `redteam-fix-all-over-defer` 第三变种):我一开始把它当"Day-8 语义边界"想
   defer,被否。现门=图独家引用答案的实义词必须 grounded 在**完整被引 chunk ∪
   问题 ∪ 数词/骨架词**,否则拒答。**fail-safe 会偶发过度拒答**(如实标注,不
   粉饰零误拒)。我自查修了一个 false-positive(只拿 quote 片段做 grounding
   导致答案引 ICN id 被误拒→改成拿完整 chunk 文本)。

## 3. git / tag 状态（勿重做）

- commit `dd210e3 feat(day12): …(v1.2.0)`,直接 ff 到 `main`(分支从 main 开、
  线性,无 PR)。tag **`v1.2.0`** 打在 `dd210e3`。
- `main` 与 `v1.2.0` **均已 push 到 origin**,与 origin 同步。
- `feat/day12` 分支可删(一天一分支);**`feat/day13` 未开,下个 session 从 main
  HEAD 开**。
- 验证:`make test`(404+9)、`make lint`;`uv run python
  tools/gen_benchmark_tables.py --check`(README 与 artifacts 一致)。

## 4. 环境事实（新 session 无需重建）

- **Vespa**:`learnarken-vespa`,`127.0.0.1:8080/19071`。当前索引 **45 chunks**
  (43 文本 + 2 图),含 Day12 conflict 文本。**两容器需手动
  `docker start learnarken-vespa learnarken-neo4j`**(不随 session 自动起)。
  重跑 `learnarken index samples/package-a samples/package-c` 前**先 clear**
  (`vespa.clear()`)——index 是 upsert 不清旧,chunk_id 变了会留 stale 触发
  verify 报 foreign(本 session 踩过两次)。
- **Neo4j**:`learnarken-neo4j`,`127.0.0.1:7474/7687`。
- **VLM = MiniMax 代理**(`mini.niagaradataanalyst.com/v1`,`.env` `MINIMAX_*`
  四键):**有 vision 但不稳定**,不用新 key,详见记忆 `minimax-vision-channel`。
  订阅制→无按次预算,429 = 终止信号。
- **裁判 CLI**:`codex`(红队闸走 `codex exec --sandbox read-only`)。`agy` 在。
  `gemini` CLI 仍死。
- **新依赖**:`pillow`(Day12 加,渲染 PNG)。缓存模型未新增。

## 5. Day 13 启动 —— **性能工程 + 半日玩具 ToT**

> 范围**已裁**(`docs/discussions/day11-13-planning.md` Decision 3),但 SPEC
> 决策层仍待 Yi Xin(可"给信息我总结转录"如 Day11/12)。**先走 step 1 研→读→扫**:

### 5.1 前置资产状态（下个 session 先补齐）

- **研**:`docs/tutorials/16-performance-engineering.md` 在档;**Day 13 DR 报告
  未见按名归档**(deepresearch 目录没有 day13/性能 命名的文件)——**先核实是否
  存在/换名,不在就请 Yi Xin 跑 研 或用 agy 兜底(标注 simulated)**,别静默跳过。
  深研提示词在 `docs/tutorials/deep-research-prompts.md`(Day 13 已在库)。
- **扫**:`docs/research/day13-unknowns.md` **缺,是 step 1c 待做**(AI 写,标注,
  按 Anthropic 盲区四象限)。
- **spec**:`docs/specs/day13.md` **缺**,决策层待 Yi Xin。

### 5.2 已裁范围（planning Decision 3,面试定位=把正确直觉换现代术语+证据）

- **四层各挣一行基准**:
  - **asyncio**:Semaphore 限流批量 VLM/embedding 调用,串行 vs 并发 wall-clock。
  - **multiprocessing**:分片校验扩展曲线 1/2/4/8 worker + 拐点分析(正好落实
    INV-2 分布式接口)。
  - **profile→numba**:py-spy 定位**真**热点,三列对比,**收益小如实报小**。
  - **Rust/PyO3**:仿 Day4b **证据开门**——profile 证明 Python 侧是瓶颈才立项,
    不开门就写留痕结论(知情消费者姿态:Tantivy/Qdrant 即 Rust)。
- **搜索类不专开一天**:并入**半日玩具 ToT**——修复 agent(Day7)单候选 vs 3 候选
  + 沙箱验证器打分,报**修复成功率 × token 成本两列**;候选生成并发化正好用上
  本日 asyncio。评估集=package-b 违规清单。"何时不值得上搜索"的实测本身是面试
  资产。
- 叙事:从"我避免并发"改写为"我避免共享可变状态"(对应 asyncio 单线程 + mp
  进程隔离)。目标 tag `v1.3.0`。

### 5.3 红队/诚实预告

- 性能基准最易造假:**固定 seed、报 wall-clock 分布不报单点、小收益不吹**
  (numba/Rust 收益经常小,如实报是纪律不是失败,延续 Day4b)。
- ToT 是非确定生成器:**重复测、报稳健不报噪声均值**(记忆
  `honest-nondeterministic-eval` + `verify-real-signal-before-acting`)。

## 6. backlog / 未办尾巴

- **⚠️ 幻觉边界分级配置表**(Yi Xin 2026-07-20 提,`docs/notes/day12-hallucination-boundary.md`):
  当前自由文本门是"一刀切"会偶发误拒;方向=按后果分级(颜色可容忍/扭矩零件号
  硬拒)的 config 表。安全档确定性、config 人定(类 BREX)、"allow-with-flag"会
  引入第 3 种结果冲击 Day5 两结果不变量。**独立议题,可专议或并入某日。**
- 多模态二次看图"**答案从再读构造**"(本日只做 fail-closed 确认,答案增益记
  Roadmap;真实有损图才有价值)。
- Day8 遗留(数字/单位感知匹配、裁判熔断、index content-hash/epoch)。
- PPR/图算法排序、LLM/NER 实体链接兜底(Day11 Roadmap)。

## 7. 高价值教训（面试素材 / 已入记忆）

1. **单次读不可信要共识、回归先量生产路径**(`verify-real-signal-before-acting`):
   Yi Xin 本 session 两处纠正,共主题"别拿不足/代理信号行动,先取可信信号"。
2. **别用'这是 DayN 边界/超范围'把难改的红队发现自我降级**
   (`redteam-fix-all-over-defer` 第三变种):尤其触及项目核心红线(fail-closed
   不幻觉)时——自由文本幻觉那次被 Yi Xin 否掉,当天在引用确证处堵死。
3. **诚实纪律帮我抓到自己的 bug**:grounding 门的 false-positive 是靠 eval 里
   A4 突然 2/4 露馅→查 trace→定位→修的。评估如实报,才照得出实现的洞。
