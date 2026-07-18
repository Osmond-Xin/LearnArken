# Day 6 Learning Journal

> Human-written; AI does not ghostwrite. (INV-6) Three fixed questions — each
> answer must contain at least one concrete instance. No platitudes.

## 1. What did I learn today?

- 本次其实是我比较熟悉的内容，但是让我学到的是契约式的API，以及需要有多个Agent来防止恶意的查询，即一个Agent执行，另外一个Agent去进行全局控制，以避免执行Agent被污染后，全局因为权限太大而出现问题。
- SSE的后端。以及哑前端是整个系统设计的一个关键。确保在前端不要有逻辑相关的内容，尤其不要有大语言模型构建相关的内容，以保证不会进行逻辑漂移。同时的话，这是AI时代的前后端的分离。所有的大语言模型相关的由后台负责，这样的话整体的迁移控制以及相应的调试都会非常的简单直接。而前端只做最基本最简单的哑前端。
- AI的session需要由后台去标记，它没有之前的HTTP请求的那种的原生的session，所以现在的session需要由后台系统自己维护。不能说叫session，应该叫request。这点是需要在开发的时候注意的，同时需要去兼顾它的可调试性。否则的话，如果在后台没有这种的request的标记的话，整体会混乱以及不可调试。


## 2. Where was the AI wrong, and how did I find out?

这部分的整体开发的准则和内容相对来说比较标准化，所以没有什么错误的。不过红队确实发现了一系列问题，但是没有P0级别的。所以在开发的过程中，没有什么AI出错的。

## 3. What AI proposal did I reject, and why?

今天在执行的过程中，发现了一个和前面预设不同的问题，即前面要求审核以后再呈现给客户，而SSE流式生成的话，等于没有把完整的内容进行审核，就展示给用户了。所以在这个情况下，我进行了一次修改，即用户体验和信息准确性之间的一个平衡。让用户看到结果，但是如果出现问题能够撤回，以保证用户体验和信息准确都能达到。当然了，它可能会牺牲一部分的用户体验，因为用户预期肯定是达到一个准确的，但实际上这个是避免不了的。所以目前来说，告知系统的思考过程，如果出错的话及时撤回，相信用户是可以理解，以及这是最优解。

## Today's numbers (if any)

总分10分，打7分。