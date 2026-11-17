# 一个静态规则怎么抓 eval harness 的假分值

> 草稿。所有数字都能在本机复跑：`score-line-audit/`（仓库内），语料在 `~/eval-audit-corpus/`。

## 问题的位置

大模型评测的复现争议，通常吵在两头：模型版本、随机种子、提示词。中间那层很少有人查——
**把 episode 结果折算成 leaderboard 数字的那段代码**。

原因是它看上去太简单：

```python
rewards = [r.reward for r in results]
avg_reward = sum(rewards) / len(rewards)
```

两行，没有歧义，谁会写错？

我拿五个公开 harness（tau-bench、simple-evals、lm-evaluation-harness、SWE-bench、
llm-bulls-and-cows，1059 个 `.py`）扫了一遍，报出 20 处。其中 16 处是同一个形态（下面会讲），
最早找到的两处在 tau-bench：

- `tau-bench/tau_bench/run.py:93` 把异常写进 `result.info["error"]`，`:186` 却用
  `sum(rewards)/len(rewards)` 把所有行都算进分母——**模型答错和程序崩了，在分数上是一回事**；
- `:184` 用 `len(set(r.trial))` 定 trial 数、`:198` 用 `comb(c,k)/comb(num_trials,k)` 算
  Pass^k。只要某任务的行数少于全局 trial 数，这个概率会超过 1。

## 为什么静态分析能抓

因为这类缺陷有一条**稳定的形状**：一个分数聚合点（`sum(x)/len(x)`），加上一个错误通道
（`info["error"]`、`except` 分支、NaN 占位值），两者之间**没有排除**。

工具叫 scoreline，四条规则，每条都先写清「什么情况下不报」：

| 规则 | 抓什么 | 沉默条件 |
|---|---|---|
| A `ERROR_FOLDED_INTO_SCORE` | `sum(x)/len(x)` 把错误行算进分母 | 有排除守卫（推导式 if、布尔索引、`continue`、条件 append） |
| B `DENOMINATOR_DRIFT` | `comb(c,k)/comb(n,k)` 的分母来自全局 trial 数 | 分母绑定在循环变量上 |
| C `ERROR_TEXT_AS_OUTPUT` | `except` 里给输出字段塞一段错误文案 | 同函数不涉及评分；已留错误字段 |
| D `DATAFRAME_ERROR_FOLDED` | `df[...].mean()` 前没排除错误行 | 过滤在本函数内可见；数据来自别的函数；在 `if` 里 append |

规则 D 是最后加的，也是最难的：现代 harness 全用 pandas，而我对 tau2-bench 660 个文件
报 0 命中——**那个 0 分不清「干净」和「射程外」**。加上 D 之后报 2 条，读源码发现都是假阳
（过滤写在调用方的另一个函数里 / 条件是枚举名 `SCORED`）。改成「证据不足就沉默」后回到 0。

**这个 0 和之前那个 0 不是一回事**：前一个是没看见，后一个是看见了两个疑似点、判定证据不足。
区别在于花了什么代价。

## 关键一步：不跑模型，判「缺陷有没有改已发布分数」

静态分析只能证明「代码有这个形状」，不能证明「分数真的错了」。要证明后者，本来得重跑
benchmark——200 个 episode、几次模型调用、一个下午。

但其实不需要。tau-bench 的 `display_metrics` 是纯函数：输入 `results`，只 print 不返回。
于是可以：

1. 从源码里用 `ast.get_source_segment` 把**上游那个函数原样取出来**，`exec` 进一个注入好
   `List`/`EnvRunResult`/`comb` 的命名空间；
2. 喂它官方仓库自带的 `historical_trajectories/*.json`（4 份真实 run）；
3. 捕获 stdout，解析出平均分与 Pass^k。

跑的是它的代码，不是我的复写。结果：

- 4 份真实 run 上，我的复算与原算法**误差为 0**，与 README 的 leaderboard 对照 16 格里 15 格
  吻合（唯一差的 `sonnet-35-new-airline` Pass^4 是 0.2243 vs 0.225，四舍五入边界）。也就是说
  **已发布的那批数字没有因为这处缺陷而变**——它们在每个任务的 trial 数相等、且没触发异常时
  是等价的。
- 那么缺陷在什么时候咬人？我人为注入：
  - 一个任务 4 次全失败 → Pass^1 `0.6043 → 0.6000`；
  - 10/115 个任务全失败 → `0.6043 → 0.5674`，**−0.037**；
  - 更糟的是「把坏任务整个剔掉」这种修法：分数变成 `0.6214`，比原来还高——只能连覆盖率
    一起报（`0.6214 on 105/115 tasks`）。

这就是「复现 leaderboard」永远证明不了的事：**顺利跑完的 run 不会触发缺陷，所以复现成功
不能当作「缺陷无害」的证据。**

## 下游反应

tau-bench 的官方后继 tau2-bench（`c06b07dd7c4d`）把这两处都修了：`agent_metrics.py:178`
改成按 `task_id` 分组算 `pass_hat_k`，`:125` 对 `n < k` 直接 `raise ValueError`，`:139-145`
显式剔除 `INFRASTRUCTURE_ERROR` 并 `logger.warning`。

这不是「我的工具发现了它」——发现是人工读代码的结论，工具在 tau2 上是 0 命中（它用 pandas，
当时还在射程外）。但**两个仓放在一起构成完整证据**：旧版有形状且注入后会改分，新版改了形状。

顺带看到 tau2 的一贯写法：`interaction_outcome` 返回 `FAIL`/`PASS`/`UNSCORED` 三态，
`experience_counts` 在评委没跑完时返回 `None` 而不是 0。**这就是「修好了的仓」的样子**——
不是把除法改对，而是让「不可计分」成为一个能向上传播的值。

## 这个工具的边界（写清楚比写漂亮重要）

- 只 Python，只看静态语法。
- 认 `sum/len`、`comb/comb`、带错误证据的 `.mean()`；不认 `.agg("mean")`、
  `.apply(lambda ...)` 内部的算术、`groupby(...).sum()` 的加权分母。
- 语料里 110 个未报聚合点逐个分档，全部落在「这个作用域没有 error 概念」——所以在这个语料
  上 0 漏报；但错误若经函数参数传入、或编码成 `-1`/`""`，工具完全失明。
- 1059 个文件里 16 条规则 D 命中是同一形态（8 个摘要任务模板 × bleurt/bert）——
  **样本多样性比命中数更重要**，这一点上结果比我期望的窄。

## 一句总结

这类缺陷的共同点不是「算错了」，而是**把「不知道」当成一个已知值**。静态规则能抓，是因为
这种折叠在代码里留下固定形状；抓不全，是因为「不知道」有很多种伪装方式。
