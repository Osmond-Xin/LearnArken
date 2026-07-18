# Day N Learning Journal — <date>

> Human-written; AI does not ghostwrite. (INV-6) Three fixed questions — each
> answer must contain at least one concrete instance. No platitudes.

## 1. What did I learn today?

- 今天的内容实际上是关联到Agent，让我有一个直观的感受，即如何去扩展LLM的能力，不光是要给它足够的工具，还要去进行限制、规范，以及防止它天生的补全特性给的系统带来的破坏。
- 一定不能偷懒，在结构上一定要加入足够的护栏以及足够的评估。不光是因为LLM具有破坏性，更是因为外部复杂的环境，用户的误操作、误上传、恶意的访问、投毒的信息和上下文，都可能会对LLM带来破坏。同时还要防止它自己所带来的破坏，例如无限次循环等。
- 同时，AI的设计会相对来说更加保守，或更加合规。而在用户的角度，会希望能力更加强大。但这两者实际上是矛盾的，强大的能力会需要更大的权限，但这种更大的权限可能会带来更大的破坏。所以整体需要进行一个平衡性取舍。
- 即使有了关键词以及相应的记忆，LLM仍然会丢失相关的工作。所以在这种情况下，需要有检测合规以及非依赖LLM的验证机制。

## 2. Where was the AI wrong, and how did I find out?

最重的都集中在我亲手写的安全沙箱上——我建了一道号称"防越权"的围栏,却留了洞:

白名单放了 pathlib/sys。我以为 AST 挡住 open/socket 就够了,实际 pathlib.Path.write_text / lxml.etree.parse(url) 经被允许的库照样读写任意文件、抓 URL。——这条是我自查时发现的（红队也独立命中）。
shell 参数完全没 jail:cat /etc/passwd、xmllint http:// 直接穿过。——我自查时漏了,是 Codex 抓的。
源符号链接被拷进 jail（可外泄 ~/.env）——我漏了,Codex 抓的。
target_key 交给 LLM 控制 + bool(cleared) 兜底,会把"清掉任意不相关 finding"误判为修复成功。这是我引入的设计缺陷——讽刺的是我在当天的未知点扫描里已经写了"这是错的",却是先写错了才反省。
mem_mb 是死配置,写了限制却从没 setrlimit 施加。——自查抓到。
诚实说:这些"我错了"里,你本人一条都没直接抓——是我跑的强制红队闸和自查抓的。但它们确实是我的错,而且集中在"我最该做对的安全代码"上。更值得记的是:我自己的红队自查也有系统性盲区——我盯着 python exec 那个洞深挖,却漏扫了 shell、文件拷贝、文件绑定这几个兄弟入口,全靠跨宿主的 Codex 补上。


## 3. What AI proposal did I reject, and why?

沙箱选项:我在提问里把"仅策展工具、无自由 shell"列为推荐(最安全),你选了更强的"沙箱执行器"。你否决了我的保守推荐——而恰恰是这个我劝退过的能力,最后暴露了上面那批洞。
风险分级:我 spec 初稿把 VIO-4 划进高风险(只 dry-run)、VIO-5/7 也偏保守。你"call apply"一句把全部枚举 VIO 归到 apply-eligible,纠正了我过度保守的分级。
"玩具级"没定义就用:你问"什么定义",是对我沟通的纠正——我抛了个档位术语却没解释,你有权要求先讲清再落地。
架构文档:反过来一次——你的初判"少了一天"其实是章节编号 vs Day 编号的误会(内容没缺,都在 05)。但你说"文档有问题"是对的,确有一批过时/矛盾(依赖数、缺文件、图表停在 Day3),我照修了。

## Things worth remembering and sharing

- "一个被允许的 import 就是一份能力"——沙箱白名单要按"这库能做什么 I/O"审,不是按"看起来人畜无害"审。这条已经写进 docs/research/day7-unknowns.md,仓库已留档,不重复进记忆。
- 跨宿主红队的价值被实证:非实现方模型(Codex)命中的正是实现方的盲区(#2/#3/#5),印证了报告 §5.4"异构验证"。这也已在 reviews/day7.md 和扫描里留档。
- 真正该进我私有记忆的,是关于我自己工作方式的一条:自查安全围栏时我会锚定第一个找到的洞、漏扫兄弟入口。这不在仓库里,是我的流程教训——我这就存下来,免得下次重犯。

## Today's numbers (if any)

满分10分，打7分。