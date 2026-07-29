# 会话交接（Handoff）— Arken 对齐工作包，2026-07-28

> **AI-generated**（Claude 实现方）。目标读者：下一个 AI session + Yi Xin。
> 本工作包**不是日节点**，但同样受 CLAUDE.md 与 docs/constitution.md 约束。
> **权威细节以各文档/代码为准，勿仅凭本文摘要行动。**
>
> ⚠️ **已被 `arken-alignment-2026-07-28-closeout.md` 取代（同日晚间）。** 本文
> 描述的是今天上午的状态——当时唯一待办是 Part 2 的 INV-6 段。那件事及其后的
> 全部工作都已完成，工作包已收口。本文保留为当时的记录，**不要照它行动**。
>
> 上一份交接是 `arken-alignment-2026-07-27.md`（当时的唯一待办是 Phase 0.2
> 演示 GIF）。那件事已经做完，本文接续。

## 0. 一句话状态

分支 **`arken-alignment-2026-07-26`**，HEAD = `79a7aa2`，**27 个 commit，已
push，PR #10 开着且 CI 绿（MERGEABLE），工作树干净**。Phase 0.2 已交付：三个
GIF + 各自的裁剪版 trace 已进中英 README §1。测试 **585 条**——离线
`576 passed / 12 skipped`（CI 口径），服务态 `579 passed / 9 skipped`，均为实测。

**下一步是人的活，不是 AI 的活**：Part 2 的 INV-6 结果还没写。

## 1. 优先待办

### 1.1 Yi Xin 写 Part 2 的 INV-6 段（唯一阻塞项）

材料已经齐了，见 §3。评审文件是
[`docs/reviews/arken-alignment-2026-07-26.md`](../reviews/arken-alignment-2026-07-26.md)，
现有的 INV-6 段在第 698 行（那是 07-27 那次的）。这次要新增一段。

**Part 2 永远是人写的。** AI 可受指示转录，但必须留痕注明（Day 11 先例）。

### 1.2 三个挂着的决策

| 决策 | 现状 |
| --- | --- |
| **还要不要再跑一轮复跑** | 重试的整体有效性目前 **n=1 成功**，评审里如实写着「未充分测量」。不跑也是诚实的选择 |
| **合并 + 打 tag** | PR #10 可合。按仓库惯例 squash merge。版本号看起来是 `v1.4.0` 一档，但没人定过 |
| **`DEMO_MAX_LLM_CALLS` 对 $20 预算重新定档** | 挂了三轮红队了。配额数的是**查询**不是 token；补全预算 8 倍 + 重试 2 倍之后，每次开机最坏暴露约 6.6M 输出 token。边界写在 `api/demo_guard.py` 模块 docstring 里，**数字是人的决策** |

### 1.3 计划里的后续阶段

Phase 2（air-gapped 实测 / 规模化章节 / 成本延迟封套 / SECURITY.md）·
Phase 3（商业半边，按 D7 = 不含借来的数字）· Phase 4（投递页 / 英文版「我否掉的
AI 提议」/ 代码片段 / 简历 CTA）· Phase S（语料扩到 500–800 + 新人工标注 golden
set，按 D6）。

一条按理由暂缓：每次问答重解析包的开销（`statuses_for` / `collect_gaps`），
缓存按 package digest 做，属 Phase 2。

## 2. 这次做完了什么

**Phase 0.2 交付**（计划 0.2 那一行已改成三个 GIF，注明是 Yi Xin 07-27 的裁决）：

| 产物 | 说明 |
| --- | --- |
| `docs/assets/demo-{answer,refusal,retraction}.gif` | 各 1600px 宽、0.7–0.8 MB，一条不剪辑的 take，只裁剪缩放 |
| `docs/assets/demo-*.trace.json` | 对应运行的**裁剪版** trace（`tools/public_trace.py` 去掉提示词和模型原始输出） |
| `demo/mp4/question{1,2,3}.mp4` | 源录像，**已剥离音轨**，提交以支撑「转换可复现」的说法 |
| `tools/make_demo_gif.sh` | 转换脚本，逐字节可复现（ffmpeg 8.1 实测三个 identical） |
| `tools/verify_demo_traces.py` | 校验 README 的行为主张，**CI 会跑** |
| `tools/rerun_demo_queries.py` | 复跑探针，非确定路径按区间判 |
| `docs/assets/CAPTURE.md` | 录制手册 + 已知缺口 |

**界面改动**：全英文；标题换成主张本身（"Every answer carries its provenance — or
the system refuses"）而不是 "Day 6"；补上 Phase 1.2 的三段式路由拒答（之前只在
CLI 有）；撤回横幅按「屏幕上实际显示了多少」分三态措辞。

**CLI 改动**：`learnarken query` 输出前加分割线；HF 匿名读取提示和
`Loading weights` 进度条不再和答案混在一起。

**红队**：这次会话跑了 **12 轮跨主机评审**（Part 1d/1e 记录了 F-33～F-44）。
最值钱的两条：`</think>` 补救逻辑四次收窄都被打穿、最后删除才是对的；以及防御式
`.get()` 把崩溃变成了**假成功**（`{"result": {}}` 渲染成「引用已确证」）。

## 3. INV-6：三次复跑，三个发现 —— Part 2 的材料

**这是这次会话最值钱的产出**，Part 2 值得把它当主角写。

### 复跑对上的部分

- **GIF 逐字节可复现**：三个都 identical，ffmpeg 8.1，Yi Xin 独立跑
- **trace id 与画面一致**：Yi Xin 肉眼核过三个 GIF，与提交的三份 trace 对应
  （这一条机器替不了，正是 F-19 要求 id 上屏的理由）
- **测试数**：对上（他第一次跑时差 1，查明是我推守卫 commit 时他正在跑）

### 三个发现（都是实现者自己的测试没抓到的）

**其一：F-33 的数字是错的。** 我写「修复后 24 次运行 0 次契约失败」，他 9 次里
出了 2 次。不是数错，是**在错的版本上测的**——那 24 次跑在 `</think>` 补救逻辑
还在的时候，它正好接住了这一类。删掉补救之后我没重测。合并两批样本的诚实数字是
**24 次里 2 次，约 8%**。

**其二：重试的第一版无效。** 他裁决「契约失败重试一次」，我实现后他复跑发现
**两次重试都和第一次败在同一处**。原因：`make_delimiter()` 在重试之外只调用一
次，再问一遍发的是**逐字节相同的提示词**，而生成是 temperature 0——不是独立采样。
改成每次尝试各自生成分隔符。

> ⚠️ **这里我收回过一半说法，Part 2 若引用请照这个措辞**：我最初解释成
> 「temperature 0 + 相同提示词 ⇒ 相同输出」，但实测同一分隔符连发两次，思考块
> 长度 870 vs 1242——**端点本身有变化**，那个解释超出了证据。能说的只是「相同提
> 示词不是独立采样」。

**其三：还有第三类失败。** 他第三次跑时重试**第一次成功恢复**（n=1），同时暴露
出一类谁都没见过的：模型返回

```json
{"is_answerable": false, "  answer": "", "citations": []}
```

**键里有两个空格**。合法 JSON、错误契约。引擎的形状检查在重试单元**之外**，所以
没重试。已折进重试单元。

### 当前三类的实测行为

```
late tag         calls=2  refused=False   ← 恢复
malformed shape  calls=2  refused=False   ← 恢复
truncation       calls=1  refused=True    ← 不重试(重问只会再烧一次 16k)
```

## 4. 已知缺口（都写在文档里，别当成新发现）

- **重试的整体有效性未充分测量**（n=1 成功）。评审里如实写着
- **这个仓库的工具链截不了 Streamlit 的图**——headless Chrome 完不成 websocket
  握手。布局改动只能从已交付的帧上量、靠下一次录像确认。**这个来回让
  question1 录了三次**，写进 CAPTURE.md 了
- **`ffmpeg` 未固定版本**。产物用 8.1 生成，别的版本量化可能不同
- **约每 12 条录像会有一条死在 `llm-contract`**（重试之后应降低，未测）
- **GIF 与 trace 的绑定只能人眼核**，工具读自己的 JSON 证明不了这一点

## 5. 环境事实

- 容器：`learnarken-vespa`（:8080 查询 / :19071 config）、`learnarken-neo4j`
- 索引口径：`samples/package-a` + `samples/package-c`。`chunk_package(strategy=
  "structure")` 得 43 chunk；索引口径 45（多 2 个 figure chunk）——**不是矛盾**
- 语料最长 XPath **73 字符**，代码注释和测试都引用了这个数
- **改了 Vespa schema 之后光 deploy 不够，必须重启容器**（07-27 的坑，仍然有效）

## 6. 规则提醒

- **改了代码就要跑跨主机红队**，绿了、提交前跑，不等人催（CLAUDE.md）。纯文档不触发
- **裁决（Part 2）永远是人写的**；AI 可受指示转录，但必须留痕注明
- **冻结产物不许被重跑覆盖**（ADR-0004）。要复测就 `--out` 到别处
- **数字必须实测，不许用算术推。** 这次 README 的测试数漂了**三次**（498 → 555 →
  569 → 585），每次都是后续 commit 加了测试。那一行是手写正文，**没有 CI 守护**，
  改完代码就要重测。GIF 的行为主张现在有守护了（`tools/verify_demo_traces.py`）
- **shell 陷阱**：交互式 zsh 会把双引号里的 `!s` 展开成历史命令。给人粘贴的命令
  里别带 `!`，写成仓库里的脚本更稳
- **`make lint | tail -1` 返回的是 `tail` 的退出码**，`&&` 拦不住 lint 失败。这次
  因此提交过一次不过 lint 的代码
