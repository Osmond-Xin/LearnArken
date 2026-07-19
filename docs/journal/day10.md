# Day 10 Learning Journal

> Human-written; AI does not ghostwrite. (INV-6) Three fixed questions — each
> answer must contain at least one concrete instance. No platitudes.

## 1. What did I learn today?

- 人类在沟通和演示的场景上，要比AI充分了解情况和更能分析的。所以在对人、对事、商业行为演示分析的时候，一定是要人类主导。
- AI并不了解它之外的人类资源，所以它给出的规划一定是受限的。换句话说，人一定要替AI去了解全景，了解资源，以及了解未来的趋势和走向。这一点是AI无论如何都代替不了的。

## 2. Where was the AI wrong, and how did I find out?

- 门控是假的——我做了 token 门控，却只挡 VM 开机，Streamlit :8501 一起来就公网裸奔。我把"挡住花钱的动作"当成了"挡住 app"。
- 成本围栏没围住真花费——SPEC 里我把"30min 自关 + $20 告警"写成成本控制，但真正烧钱的 MiniMax 每次调用零拦截。
- fail-closed 装置实际 fail-open——我写的看门狗遇到畸形 /demo/status 会崩溃、硬顶用可重置的进程时钟，本该自关反而永不关。
- 兄弟入口漏——我特意把 /demo/status 做成只回布尔防泄露，却漏了 Streamlit 还在调的 /health。我自己在 unknowns 的 T2 写了这个风险还是漏了。

## 3. What AI proposal did I reject, and why?

- AI锚定在"只能上免费层"的框架里，把方案 A（免费层简化切片）作为讨论起点推给我。是我用「有 AWS/GCP 付费账户 + 对方触发才启动」把选型空间整个重构成「按需真栈」——这个更优解是我提的，不是我。根因是我沿用了自己 Day9 handoff 里写的约束，没在动手前核实"我手上到底有什么资源"。
- 我让AI"检查 MiniMax 费用拦截是否还在"——我的直觉部分对：它存在，但只在 Day 7 的 repair 子系统，问答路径本来没有。我这一问逼出了一个我没主动去核的缺口。

## Things worth remembering and sharing

- 更新 [[security-fence-self-review-blindspot]]——这是老盲区（Day7 沙箱、Day9 死链守卫），Day10 一次会话四发 + 修 fix 又留后门，证据够硬。我把可操作规则升级了：不只"漏扫兄弟入口"，而是对每道守卫先一句话写清它声称保护什么（哪个不变量/哪笔成本/哪条边界），再专门找这句话不成立的输入或路径（畸形输入、默认/占位值、被保护资源本身而非代理指标、功能对称的兄弟入口），并加一条"改完围栏再自问有没有引入默认可用后门"。

- 新建 [[assumed-constraint-anchoring]]——"我会把继承来的约束当既定前提在里面优化，不先核实真实资源"。这是本次最有价值的新教训，和上面那条同源（都是"没回到第一性核对自己继承的前提"），可操作规则是动手选型前显式列约束 + 主动问"你手上有哪些账户/资源/预算"。

## Today's numbers (if any)

满分10分得8分。