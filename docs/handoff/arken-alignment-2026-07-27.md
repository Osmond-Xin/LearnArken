# 会话交接（Handoff）— Arken 对齐工作包，2026-07-26/27

> **AI-generated**（Claude 实现方）。目标读者：下一个 AI session + Yi Xin。
> 本工作包**不是日节点**，但同样受 CLAUDE.md 与 docs/constitution.md 约束。
> **权威细节以各文档/代码为准，勿仅凭本文摘要行动。**

## 0. 一句话状态

分支 **`arken-alignment-2026-07-26`**，HEAD = `405f27c`，**5 个 commit，工作树干净，
未 push、未开 PR**。`make lint`（现已覆盖全仓库）通过；**498 条测试：离线
`486 passed / 12 skipped`，服务起着时 `489 passed / 9 skipped`（均为实测，非推算）**；
基准表与产物一致。Phase 0（除 0.2）与 Phase 1 全部完成，三轮红队 32 条发现全修，
Part 2 裁决已按 Yi Xin 原话转录。

## 1. 明天要做的唯一一件事：Phase 0.2 演示 GIF

**只能人做**（需要真栈 + 录屏）。计划明令**禁止摆拍**。

### 1.1 先读这条——它决定了你能拍到什么

我今天用 SSE 实测过两条 query 的事件序列，结论会改变你的拍摄预期：

| 问题 | 事件序列 | 能不能拍到「文字出现又被撤回」 |
| --- | --- | --- |
| `APU automatic start sequence` | `status×3 → **retract** → result → done`，**`token: 0`** | **不能**。撤回协议**确实触发了**，但模型在吐出任何答案文本前就判定 `is_answerable: false`，所以没有可见文字被撤走 |
| `What safety precautions apply before removing the hydraulic pump?` | `status×3 → token×2 → result → done` | 不适用（这是成功作答） |

**也就是说：能稳定复现的是「撤回事件」，不是「文字先出现再消失」那个戏剧性画面。**
后者需要模型先流式吐出答案文本、再被 `citation-validation` 门作废，而那是**非确定性
的**——没有任何环境变量能强制触发（我找过，`engine.py` 里没有这类开关）。

复现命令（不用起 Streamlit）：

```bash
uv run python -c "
from fastapi.testclient import TestClient
from learnarken.api.app import app
r = TestClient(app).post('/query', json={'question':'APU automatic start sequence'})
print([l[7:] for l in r.text.splitlines() if l.startswith('event: ')])
"
```

### 1.2 两个方案，按计划的诚实约束

**方案 A（保底，建议先拍这个）**：拍可复现的那条链
`提问 → status 心跳 → retract → 拒答并报出门名`。
**GIF 说明文字必须如实写**：这次运行里模型在流式输出答案文本之前就判定不可答，
所以撤回事件触发了但没有可见文字被收回。**这不是缺陷，是诚实。**

**方案 B（机会主义，能碰上就拍）**：多试几个「看起来像能答、但引用站不住」的问题，
等 `citation-validation` 门在流式之后触发。碰上了就拍，**碰不上不许伪造**。

无论哪个方案，按红队 F-19：**GIF 必须连同那次运行的 trace id 一起提交**
（`docs/assets/demo-retraction.trace.json`），因为 GIF 是全仓库唯一没有复现路径的产物。

### 1.3 执行步骤

```bash
# 1. 起服务（Vespa 首次就绪约 30s）
docker start learnarken-vespa learnarken-neo4j
until [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ApplicationStatus)" = "200" ]; do sleep 5; done

# 2. 索引状态自检——如果 schema 或语料动过，这里会 fail closed 并告诉你怎么办
uv run learnarken query "hydraulic pump" >/dev/null && echo "index OK"
#    若报 "manifest schema digest ... != current"：
#    uv run learnarken index samples/package-a samples/package-c

# 3. 起 demo（FastAPI :8100 + Streamlit :8501，Ctrl-C 同时停）
make demo

# 4. 录屏，产物放这两个路径（<5 MB）
#    docs/assets/demo-retraction.gif
#    docs/assets/demo-retraction.trace.json     ← GIF 里那次运行的 trace
```

拍完后把 README 里 Phase 0.2 的位置补上图（§1 三段终端输出之后是自然位置）。

### 1.4 ⚠️ 今天踩到的坑，别再踩一遍

**改了 Vespa schema 之后，光 deploy 不够，必须重启容器。**
`security_classification` 加 `attribute` 那次：deploy 报成功、config server 显示新
generation、清空重灌都做了，content node 照样报 `attribute not found`，**重启容器才
生效**。已加 `assert_attribute_filtering_supported()`（喂数前发一条 hits=0 探针查询）
把这个失败变成可见的报错，但**修复动作仍然是重启**。

## 2. 已完成的东西在哪

| 产物 | 路径 |
| --- | --- |
| 执行计划（rev 2，§7 是状态总表） | `docs/specs/arken-alignment-2026-07-26.md` |
| 三轮红队 + Part 2 裁决 | `docs/reviews/arken-alignment-2026-07-26.md` |
| Arken 源快照（含此前漏读的 /trust、/deploy、/whitepapers） | `docs/research/arken-source-snapshot-2026-07-26.md` |
| ADR-0004（素材改了测量就作废） | `docs/adr/0004-measurements-are-bound-to-their-corpus.md` |
| 新代码 | `src/learnarken/{clearance,gaps,owners,refusal,citation_status}.py` |
| 新测试 | `tests/test_arken_alignment.py`（38 条）、`tests/test_readme_guards.py`（5 条）|

## 3. 三个结构性发现——最值钱的东西，别在后续会话里丢

**fail-closed 的入库闸门，让 Arken 的三条性质在结构上够不着**，而处理方式统一是
「照算、如实报空」，不是假装实现：

1. **Gap**：声明缺失的模块是入库 *error*，所以携带它的包永远不会被准入 ⇒ Arken 定义的
   「已准入知识的 gap」不可能出现。交付的是 `pre_admission_declared_missing`。
2. **拒答 owner 路由**：按裁决只从 admitted gap 路由 ⇒ 当前语料上什么都路由不到。
3. **引用状态**：入库拒收 XREF-003 不匹配 ⇒ 已准入语料上恒为 `current`。

这三条在 README §6 和代码 docstring 里都写明了。**它们是卖点不是缺陷**——诚实地说明
「为什么在这套架构下够不着」，比凑一个假实现有说服力得多。

## 4. 还欠着的（按优先级）

1. **Phase 0.2 GIF** —— 明天，见 §1
2. **push + 开 PR** —— 分支已 5 个 commit，尚未 push
3. **Phase 2**（air-gapped 实测 / 规模化章节 / 成本延迟封套 / SECURITY.md）
4. **Phase 3**（商业半边，按 D7 = 不含借来的数字）
5. **Phase 4**（arken-alignment.md 投递页 / 英文版「我否掉的 AI 提议」/ 代码片段 / 简历 CTA）
6. **Phase S**（语料扩到 500–800 + **新人工标注 golden set**，按 D6）
7. **一条按理由暂缓**：每次问答重解析包的开销（`statuses_for` / `collect_gaps`），
   缓存按 package digest 做，属 Phase 2

## 5. 环境事实（新 session 无需重建）

- 容器：`learnarken-vespa`（:8080 查询 / :19071 config）、`learnarken-neo4j`（:7474/:7687）
- 索引口径：`samples/package-a` + `samples/package-c`，45 chunks（含 2 个 figure chunk）
- `make lint` **现已覆盖全仓库**（原先只有 `src tests`，`tools/`、`deploy/` 因此腐烂过）
- `make test` 服务态 `489 passed / 9 skipped`；离线 `486 passed / 12 skipped`

## 6. 规则提醒

- **改了代码就要跑跨主机红队**，绿了、提交前跑，不等人催（CLAUDE.md）。纯文档不触发。
- **裁决（Part 2）永远是人写的**；AI 可受指示转录，但必须留痕注明。
- **冻结产物不许被重跑覆盖**（ADR-0004）。要复测就 `--out` 到别处。
  `tools/day11_refusal_gate.py` 已经支持 `--out`，其余工具没有，动之前先看。
- **数字必须实测**，不许用算术推。今天有一次差点用推算填 README 的测试数，
  停下来跑了一遍才写。
