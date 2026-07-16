# 01 · 文件清单：每个文件在做什么

> **AI-drafted，待人审**。快照：2026-07-15，分支 `feat/day3`（Day 3 已实现、
> 红队已裁决，尚未合并打 tag）。行数为快照当日实际值，仅示意规模。

## 一、根目录：工程骨架（Day 1）

| 文件 | 职责 |
| --- | --- |
| [pyproject.toml](../../pyproject.toml) | 项目元数据与依赖单一事实源。运行时依赖仅 4 个（defusedxml / lxml / pydantic / rank-bm25），全部带上界 + `uv.lock` 锁定（Day 2 红队裁决 #13：解析器行为不许在未锁定安装下漂移）。注册 CLI 入口 `learnarken = learnarken.cli:main`。 |
| [uv.lock](../../uv.lock) | 依赖锁文件，CI 用 `uv sync --locked` 安装，保证可复现（INV-5）。 |
| [Makefile](../../Makefile) | 三个入口：`make test`（pytest）、`make lint`（ruff check + format --check）、`make fmt`（自动修复）。 |
| [.pre-commit-config.yaml](../../.pre-commit-config.yaml) | 提交前钩子：ruff 检查/格式化 + 大文件/合并冲突/私钥泄漏/行尾空白检查。**detect-private-key 是安全红线的机器执行层**。 |
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | CI：锁定安装 → lint → test。action 全部按 commit SHA 固定（防供应链漂移）。 |
| [.gitignore](../../.gitignore) | 首个 commit 即配好：`.env`、密钥、缓存不入库（安全红线）。 |
| [README.md](../../README.md) / [README.zh-CN.md](../../README.zh-CN.md) | 对外门面：业务场景、AI-first 工作流说明、进度表、**Day 3 检索基准表**（含复跑命令）、诚实分层 Roadmap、仓库导览。对外一律英文（中文版为镜像）。 |
| [CLAUDE.md](../../CLAUDE.md) | AI 实现方的操作规则：角色边界（SPEC 决策层人写、journal/裁决 AI 不碰）、自动红队闸、当日讨论纪要强制规则。 |

## 二、src/learnarken/ — 产品代码

### 2.1 核心解析与模型（Day 1–2）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [package.py](../../src/learnarken/package.py) | 166 | **Day 1 的轻量扫描器**：只解析 inspect 摘要表需要的字段（dmCode、标题、issueInfo、语言），直接读 XML 属性。含控制字符清洗（红队 #9：防标题里的 ANSI 序列污染终端）。是 `inspect` 命令的后端。 |
| [models.py](../../src/learnarken/models.py) | 175 | **Day 2 规范模型（Pydantic）**：DmCode、DataModule、PublicationModule、DML、DmRef/IcnRef、warning/caution、Applicability（displayText + 结构化断言双轨——断言给 Day 3 chunk 做机器过滤，displayText 给人读）。全仓库的"规范数据字典"。 |
| [loader.py](../../src/learnarken/loader.py) | 300 | **XML → 规范模型的装载器**：每个文件先过 defusedxml（L0 良构性 + 防实体炸弹），再由加固的 lxml（禁实体/DTD/网络）重解析拿行号、XPath、XSD 校验。含 fail-closed 文件大小上限（红队 #4：超限拒收而非耗尽内存）。 |
| [cli.py](../../src/learnarken/cli.py) | 472 | 命令行入口，6 个子命令：`inspect`（包摘要）、`validate`（四层校验，JSON/人读两种输出）、`dm`（单 DM 详情）、`chunk`（分块预览）、`search`（BM25 查询）、`eval retrieval`（golden set 评估）。 |
| [schemas/learnarken.xsd](../../src/learnarken/schemas/learnarken.xsd) | — | 项目自造的**简化 XSD**（L1 结构校验层），对真实 S1000D schema 的玩具级替身（INV-7 诚实分层）。 |

### 2.2 validation/ — 四层校验器（Day 2）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [engine.py](../../src/learnarken/validation/engine.py) | 433 | 四层编排：L0 良构 → L1 mini-XSD → L2 单文件 BREX → L3 跨文件完整性（dmRef 悬空、ICN 缺失、版本错位、循环引用）。**Fail-closed 分层（INV-4）**：L0 挂的文件不进上层；L1 挂的跳过自身 L2 但仍作为 L3 图节点存在。**L3 的引用图是未来知识图谱（Neo4j）的地基**。 |
| [rules.py](../../src/learnarken/validation/rules.py) | 169 | L2 BREX 规则表：Schematron 风格的声明式断言（rule id、severity、描述、fix hint、检查函数），不引入 isoschematron 工具链。BREX-001 是诚实标注的玩具启发式（危险词词表代替真实业务规则，INV-7）。 |
| [report.py](../../src/learnarken/validation/report.py) | 58 | 四层共用的 Finding / ValidationReport Pydantic 模型（rule_id、layer、severity、file、line、path、message、fix_hint）。 |

### 2.3 chunking/ — 结构感知分块（Day 3）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [base.py](../../src/learnarken/chunking/base.py) | 104 | Chunk 模型 + 元数据继承：chunk 从 Day 2 DataModule 继承 DMC、applicability（排除场合）、hazard 标志（紧急场合，见 discussions/day3 D4）、`outbound_dm_refs`/`icn_refs`（**图谱钩子**，D3 的"不许饿死未来图谱"义务）。chunk_id 确定性生成（内容哈希），复跑不变。 |
| [structure.py](../../src/learnarken/chunking/structure.py) | 113 | **结构感知策略（主力）**：沿文档自带的切线切——每个 procedural step 一块（行内 warning 折入并置 hazard 标志）、reqSafety 前置警告独立成块、前置条件/收尾各成块、描述节按 levelledPara 切。每块保留 XPath 锚点（golden set 按锚点标注）。 |
| [recursive.py](../../src/learnarken/chunking/recursive.py) | 74 | **递归字符窗口策略（对照组）**：故意结构盲，800 字符窗口 / 100 重叠，在词边界断开。存在的意义是让评估表**量化**结构感知值多少分。 |
| [\_\_init\_\_.py](../../src/learnarken/chunking/__init__.py) | 81 | `chunk_package` 入口：遍历包内 DM，按策略产出 chunk；复用 Day 2 loader，不重复解析。 |

### 2.4 retrieval/ — BM25 基线与评估（Day 3）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [bm25.py](../../src/learnarken/retrieval/bm25.py) | 80 | **保标识符的分词器** + rank-bm25 薄封装。核心洞察（教程 02 §1）：标准分析器会把 `DMC-LA100-…`、`P/N 1234-567` 在标点处打碎，标识符查询就被数字碎片淹没；把标识符保成整 token 是技术语料里单点杠杆最高的修复。 |
| [evaluate.py](../../src/learnarken/retrieval/evaluate.py) | 238 | golden set 评估：Recall@k（RAG 首要指标）/ MRR / nDCG，固定种子。相关性按 (DMC, XPath) 锚点判定——structure 块精确/嵌套匹配 XPath，recursive 块按 60% token 重叠覆盖（红队 R3 修复：容忍锚点被两个窗口切开）。无答案陷阱题单独算 zero-hit 率。 |
| [\_\_init\_\_.py](../../src/learnarken/retrieval/__init__.py) | 122 | `search_package` / `run_eval` 入口：内存态 BM25 索引，**无索引持久化**（语料极小，spec 明确 Out of Scope）。 |

## 三、tests/ — 测试（与实现同 PR 交付）

| 文件 | 覆盖 |
| --- | --- |
| [test_inspect.py](../../tests/test_inspect.py) | Day 1 冒烟：包扫描 + inspect CLI。 |
| [test_validation.py](../../tests/test_validation.py) | Day 2 golden 测试：每条 BREX 规则 ≥1 通过 + ≥1 违规用例（INV-3），对 package-a/b 全量断言。 |
| [test_cli_day2.py](../../tests/test_cli_day2.py) | Day 2 CLI：validate / dm 子命令。 |
| [test_adjudication_fixes.py](../../tests/test_adjudication_fixes.py) | Day 2 红队裁决修复的回归测试，每个测试注明对应裁决条目。 |
| [test_chunking.py](../../tests/test_chunking.py) | Day 3 分块：两种策略、元数据继承、**存储健全性**（chunk 数对账、ID 确定性、元数据往返、排除过滤真排除——discussions/day3 D6）。 |
| [test_retrieval.py](../../tests/test_retrieval.py) | Day 3 检索：分词器、BM25 搜索、指标计算、CLI。 |

## 四、eval/golden/ — 版本化评估资产（Day 3）

| 文件 | 职责 |
| --- | --- |
| [README.md](../../eval/golden/README.md) | 双文件双作者制的说明（检索评估的红线：**相关性判断必须人做**）。 |
| [day3.candidates.jsonl](../../eval/golden/day3.candidates.jsonl) | AI 起草的 24 个候选问题（每行标 `ai_suggested: true`），只是脚手架，**非权威**。 |
| [day3.jsonl](../../eval/golden/day3.jsonl) | **人工标注的权威 golden set**：32 题（27 可答 + 5 无答案陷阱），Yi Xin 判定相关性。README 基准表的数字来源。 |

## 五、samples/ — 合成样本包（INV-1：绝不含真实 S1000D 内容）

| 目录 | 职责 |
| --- | --- |
| [package-a/](../../samples/package-a/) | **合法包**：10 个 S1000D-like XML（描述、程序、fault、IPD、DML、PMC）+ ICN 图形。校验应全绿。 |
| [package-b/](../../samples/package-b/) | **已知违规包**：植入枚举过的违规类（VIO-1..8，清单在宪法 §4），是校验器的靶场——findings 必须与违规清单一一对应到行/路径。 |
| [package-c/](../../samples/package-c/) | **适用性排除测试包**（Day 3 新增）：验证"排除 variant X 真的排除"的指定输入，也进检索评估语料。 |
| [samples/s1000d/](../../samples/s1000d/) | 真实 S1000D 结构的**只读参考**（非提交文件仅参考、绝不复制内容）。 |

## 六、docs/ — 证据链与知识资产

| 目录/文件 | 职责 | 作者 |
| --- | --- | --- |
| [constitution.md](../constitution.md) | 最高权威：业务场景 + 8 条不变项（INV-1 数据红线 … INV-8 滑点规则）+ package-b 违规清单 | 人 |
| [execution-plan.md](../execution-plan.md) | 10 日执行主计划：每日七步循环、各日验收标准 | 人 |
| [project-design.md](../project-design.md) | 完整愿景设计（M0–M8、JD 覆盖矩阵）——执行计划只切其中最小闭环 | 人 |
| [specs/day1–3.md](../specs/) | 每日 SPEC：决策层人写，阐述层可 AI 起草（带标签） | 人主导 |
| [discussions/day1–3.md](../discussions/) | 蒸馏的设计讨论：问题→选项→决定→理由（**Day 4 选型的决策出处都在 day3.md**） | AI 蒸馏、人审 |
| [reviews/day1–3.md](../reviews/) | 红队 findings（非实现方模型出）+ 人工逐条裁决 | AI + 人 |
| [journal/day1–3.md](../journal/) | 学习日志（固定三问），**AI 永不触碰** | 人 |
| [redteam.md](../redteam.md) | 红队配方：轻量交叉评审 + 重型 Producer→Challenger→Reviser 循环 | 人 |
| [local-services.md](../local-services.md) | **本地服务手册**：Vespa/Neo4j docker 连接信息、MiniMax API 环境变量形状（无密钥值） | 人+AI |
| [tutorials/00–12](../tutorials/) | 中文零基础教程系列 13 篇（Day 4 对应 03 向量检索、04 高级检索） | AI 起草 |
| [diagrams/](../diagrams/) | mermaid 源 + 渲染 SVG：学习路线图、领域地图、架构流 | AI 起草 |
| [learning-guide.md](../learning-guide.md) / [visual-map.md](../visual-map.md) | 学习导引与视觉地图 | AI 起草 |
| [github-plan.md](../github-plan.md) / [job-search-review-2026-07.md](../job-search-review-2026-07.md) / [resume-fixes-2026-07.md](../resume-fixes-2026-07.md) | 求职侧文档（GitHub 呈现计划、求职评审、简历修订） | 人主导 |
| architecture/（本目录） | 架构快照与变更基准 | AI 起草、人审 |
