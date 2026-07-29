# 会话交接（Handoff）— Arken 对齐工作包收口，2026-07-28 晚

> **AI-generated**（Claude 实现方）。目标读者：下一个 AI session + Yi Xin。
> 本工作包**不是日节点**（它自己的 SPEC 这么写），但同样受 CLAUDE.md 与
> docs/constitution.md 约束。
> **权威细节以各文档/代码为准，勿仅凭本文摘要行动。**
>
> **本文取代 `arken-alignment-2026-07-28.md`**（那份写于今天上午，当时唯一待办是
> Part 2 的 INV-6 段）。那件事以及其后的全部工作都已完成。

## 0. 一句话状态

**Arken 对齐工作包已收口。** `main` = `a54165a`，tag `v1.4.0`，PR #10/#11/#12/#13
全部 squash merge，**工作树干净，本地=远端，四个工作分支已删**。Phase 0 / 1 / 4
（4a/4b/4c/4d）全部交付。测试 **659 条**——离线 `647 passed / 12 skipped`（CI 口径），
服务态 `650 passed / 9 skipped`，均为 2026-07-28 实测。

**Yi Xin 已准备投递 Arken 岗位。** 简历与求职信托管在站外，README §10 与
`docs/arken-alignment.md` 链接它们。

## 1. 现在没有阻塞项

工作包内已无待办。下面全是**可选的后续**，按 D4 裁定的顺序（`0 → 1 → 4a → S → 2 → 3`）：

| 阶段 | 内容 | 谁的活 |
| --- | --- | --- |
| **Phase S** | 语料扩到 500–800 + **新人工标注 golden set** | **人**。C7 已写明：标注是成本大头，不是生成 |
| **Phase 2** | air-gapped 实测（先 pin 后发数）· 规模化章节 · 成本延迟封套 · SECURITY.md | AI 可做，需先有 SPEC 决策层 |
| **Phase 3** | 商业半边（Dawson 第 2/4/10 步），按 D7 = 不含借来的数字 | AI 可做 |

**重试有效性仍然是 n=1。** 探针造好了、跑过一次、什么都没测到（24 次运行零契约失败）。
要抬这个数只能再跑，见 §3。

## 2. 这次会话做完了什么

四个 PR，一天：

| PR | 内容 |
| --- | --- |
| **#10** | INV-6 复跑探针 `tools/probe_retry_effectiveness.py` + 45 测试；Part 1f/1g；Part 2 五条裁决 |
| **#11** | Phase 4a `docs/arken-alignment.md` 长版对齐审计；README 露出探针故事；**九处夸大修正** |
| **#12** | 4b `docs/ai-proposals-rejected.md` · 4c §2 一道门的源码 · 4d §10 简历链接 + demo CTA |
| **#13** | 简历/求职信改托管站外，README 链接两个地址 |

**Part 2 里 Yi Xin 的五条裁决**（`docs/reviews/arken-alignment-2026-07-26.md`，
`### Standing ruling extended — F-33 – F-61`）：

1. 常设裁决**向前生效**——以后红队发现一律全修，缓办才需要记理由
2. 采样计划可以随测量需要改（F-56）
3. 2026-07-28 那份样本**关闭不迁移**，重开新日志（ADR-0004 的同一逻辑）
4. 花费围栏**宁可高报不可低报**，但基础要写明
5. 探针**不许写死引擎事实**，要向后兼容——并且**探针工作到此为止**

## 3. 探针：怎么用，以及一个坑

- 当前 `LOG_VERSION = probe-retry/9`
- **仓库里那份 `eval/results/probe-retry-2026-07-28.jsonl` 是 `/5` 版，`load_prior`
  会拒绝它**（`run 1 is missing trace_spans`）。这是版本闸门按设计工作，不是 bug。
  要加样本就开新日志——这是裁决 3。
- 查询组合已从 3 条改为 2 条：原来那条「coffee maker」在阈值门就被拒，**8/8 次都
  到不了模型**，占着分母却不可能贡献。现在两条都实测能到模型，所以 24 次运行 ≈
  **24 次生成**（之前只有 16 次）。

```
uv run python tools/demo_preflight.py
uv run python tools/probe_retry_effectiveness.py --runs 24 \
    --out eval/results/probe-retry-<新日期>.jsonl
```

跑之前它会打印本次会话的最坏花费和硬停点。中途 ^C 不丢已付费的观测。
**这是 INV-6 的数字，按规矩由人跑。**

## 4. 简历/求职信：位置与一个隐私提醒

- **站外托管**：`niagaradataanalyst.com/resume/arken/Yi_Xin_Resume_ARKEN_AI_Engineer.pdf`
  与 `..._CoverLetter_...pdf`。两个 URL 在链接前都实测抓取过。
- README §10 与 `docs/arken-alignment.md` 的「Why I wrote it」块链接它们。
- **仓库里没有、`main` 历史里也没有 PDF**，符合 Day 9 那条「求职私档指向公共锚点，
  反向不可」。

> ⚠️ **一个诚实的残留风险。** 这两份 PDF 曾在分支 `arken-resume-2026-07-28` 的
> commit `3db9d7b` / `947e8f6` 上**推送到过 GitHub**（含电话号码），随后被 Yi Xin
> 从版本库删除。今天已删除该远端分支，**正常访问路径已消失**；但 GitHub 对不可达
> 对象有保留期，在此期间**按 SHA 仍可能被取到**。想彻底了断需联系 GitHub Support
> 请求 GC。记在这里而不是当它没发生。

## 5. 这次会话最值钱的两条经验

**其一：读代码有上限，"跑一遍"是另一种仪器，不是更慢的同一种。**

探针跑了 **11 轮**跨主机红队，第 11 轮返回 SHIP。然后第一次真跑，当场暴露出 11 轮
都没找到的缺陷：样本里三分之一是阈值门拒答的查询，**结构上不可能产生被计数的事件**，
却待在分母里。那个为防止分母虚高而造的工具，自己的分母是虚高的。
（写在 Part 1g / README §7，是整个仓库最有说服力的一段材料。）

**其二：对外材料的缺陷几乎都不是 bug，是"多说了一点"。**

Phase 4 的六轮红队出了 18 条，几乎每一条都是措辞：「verbatim」用在缩进改过的片段上、
「Gate 11」而实际是第 10 道、「相隔九天」而实际两天、「每个数字都附**重生成**它的命令」
而有一张表今天跑不出原值。**每条都小，合起来是"经得起核查"和"经不起"的差别。**

其中三条在访客真正落地的 `deploy/trigger/index.html` 上——一个拿到 token 的面试官
第一眼看的就是它。**改对外文案时记得那个页面也是对外文案。**

## 6. 已知缺口（都写在文档里，别当新发现）

- **重试有效性未测**（n=1）。评审里如实写着
- **Day 4 消融表今天跑不出原值**：Day 12 扩了语料，32 格里 12 格漂移，
  ADR-0004 裁定留原值不改，BENCHMARKS.md 写明了
- **手写散文数字不在 CI 守卫内**。README 测试数今天漂过第四次（585 → 647），
  是靠重测发现的，不是 CI。**改完代码就要重测那一行**
- **`ffmpeg` 未固定版本**（demo GIF 用 8.1 生成）
- **这个仓库截不了 Streamlit 的图**（headless Chrome 完不成 websocket 握手）

## 7. 环境事实

- 容器：`learnarken-vespa`（:8080 / :19071）、`learnarken-neo4j`。**当前是停止状态**
- 「离线」测试口径 = **容器停着**（12 skipped）；`.env` 在不在**不影响** skip 数
- 索引口径：`samples/package-a` + `samples/package-c`
- **改了 Vespa schema 之后光 deploy 不够，必须重启容器**
- 还剩两个更早的分支 `feat/day6`（含远端）与 `feat/day12`，内容都已在 main，
  **本次未动**——要清理是独立决定

## 8. 规则提醒

- **改了代码就要跑跨主机红队**，绿了、提交前跑，不等人催。**纯文档不触发**
- **裁决（Part 2）永远是人写的**；AI 可受指示转录，但必须留痕注明
- **冻结产物不许被重跑覆盖**（ADR-0004）。要复测就 `--out` 到别处
- **数字必须实测，不许用算术推**
- **一个分支一个 PR**，CI 在**该 commit 上**绿了才合——别拿上一次的绿去合
- `make lint | tail -1` 返回的是 `tail` 的退出码；要判 lint 成败得单独取 `$?`
