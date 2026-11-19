# HN 独立数据源验证：核心结论交叉检验（2026-11-18）

## 结论（先给）

用与 ATS 聚合站**完全独立**的底物——Hacker News 社区自发招聘帖——复刻 `signals-baseline.md` §4.3 的核心结论：**方向成立，比例不成立**。八轴正则这把尺不变，底物换成 HN 后：

- `ai_only` 家族八轴均值 **0.7143 > platform_only 0.5185**（H1 SUPPORTED）——方向一致。
- `context_memory` 是 `ai_only` 头号轴 **23.81%**，平台侧只有 7.41%（H2 SUPPORTED）——头号轴一致。
- 但绝对值远低于主表（`ai_only` context_memory 65.5%）——**只能说排序一致，不能说比例一致**（H3 = 作用域守卫）。

**这才是真正的独立验证。** 先前用 freehire 官方 `ai_archetype` 的尝试被判定为同源共线（`archetype-crosscheck-2026-11-18.md`），不可当独立证据。

## 判据与预注册（verification-gate 纪律）

脚本 `signals/verify_hn_independent.py`，预注册三条假设，**先注册再看数、不为让门变绿调阈值**：

| 假设 | 内容 | 判定方向 |
|---|---|---|
| H1 | HN 帖上 `ai_only` 家族八轴均值高于 `platform_only` | `ai_mean > plat_mean` → SUPPORTED |
| H2 | HN 帖上 `context_memory` 仍是 `ai_only` 头号轴（对齐 §4.3） | top_axis == context_memory → SUPPORTED |
| H3 | 绝对值可与主表不同（HN 自选择、英文、创业公司偏多）——作用域守卫 | 恒 SUPPORTED，但比例差异必须如实标注 |

- 尺 = `signals/analyze_axes.py` 的八轴正则 `COMPILED` + `title_family`（与主表同一把尺，不换尺）。
- 底物 = HN `Ask HN: Who is hiring?` 两个线程：2026-10 objectID `49922569`、2026-11 objectID `50338728`，共 **390 条**自发招聘帖（`signals/raw/hn_hiring_posts.json`）。
- `parse_hiring_posts` 解析规则：帖子第一行公司/岗位以 `|` 分隔（≥3 个 `|`）；不满足的行不进样本。
- 最小样本守卫 `MIN_PER_FAMILY = 20`：`ai_n`/`plat_n` 各须 ≥20 才判方向，否则 NOT_RUN。

## 实测（命令 + 输出，全部 exit 0）

```bash
python3 signals/verify_hn_independent.py
# problems=0 state=EVALUATED h1=SUPPORTED h2=SUPPORTED h3=SUPPORTED
# n=390 ai_n=21 plat_n=27 one_share=0.8692 ai_mean=0.7143 plat_mean=0.5185   exit 0

python3 signals/verify_hn_independent.py --prove-red
# baseline: h1=SUPPORTED h2=SUPPORTED ai_n=21 plat_n=27 one_share=0.8692
# OK prove_red[1/3] dead grouping variable: gate refuses (NOT RUN)
# OK prove_red[2/3] empty body: H1 flips -> CONTRADICTED
# OK prove_red[3/3] trivial instrument: H2 flips -> CONTRADICTED
# prove_red: OK, HN crosscheck gate goes red under all 3 injected violations   exit 0
```

## 详细读数（逐家族逐轴）

| 家族 | n | context_memory | tool_mcp | harness | observability | 八轴均值 |
|---|---|---|---|---|---|---|
| `ai_only` | 21 | **23.81%** | 9.52% | 9.52% | 9.52% | **0.7143** |
| `ai_and_platform` | 3 | 66.67% | 33.33% | 33.33% | 0% | 1.3333（n 太小不判） |
| `platform_only` | 27 | 7.41% | 7.41% | 3.70% | 18.52% | **0.5185** |
| `neither` | 339 | 2.65% | 4.72% | 0.59% | 1.77% | 0.1475 |

- `one_family_share = 0.8692`：339/390 条落到 `neither`，即 HN 帖大多数不写 AI infra 细节——这是 HN 自述帖的固有稀疏性，不是仪器坏；脚本把它作为作用域字段落盘，不拿它算方向。
- `ai_n=21`、`plat_n=27` 刚过 `MIN_PER_FAMILY=20` 门槛——**样本量偏小是本次验证的最大边界**；结论是方向性佐证，不是精确估计。

## 与主表对照（复刻排序，不复刻比例）

| 结论维度 | 主表（ATS 聚合 n=4017） | HN 独立底物 n=390 | 一致？ |
|---|---|---|---|
| ai_only 八轴均值 > platform_only | 2.56 > 1.20 | 0.7143 > 0.5185 | ✅ 方向一致 |
| ai_only 头号轴 = context_memory | 65.5% | 23.81% | ✅ 排序一致 |
| context_memory 绝对值 | 65.5% | 23.81% | ❌ 比例不一致（底物自选择） |

## 边界（如实标注）

1. **只复刻排序，不复刻比例**：HN 帖是社区自述、英文、创业公司偏多，岗位结构与付费 ATS 库不同；绝对值差异是底物差异，不是主表错。
2. **样本量偏小**：`ai_n=21`/`plat_n=27` 刚过门槛，若 HN 换月份或换线程，方向是否稳定未测。
3. **同一把尺**：验证的是「结论不是这台仪器的伪影」，不是「换成另一套词表也成立」。换尺需另做实验。
4. **H3 是守卫不是发现**：它恒 SUPPORTED，真正防止过度解读的是把 `one_family_share` 和绝对值差异如实写进报告。

## 复现命令

```bash
cd agent-infra-kickstart
python3 signals/verify_hn_independent.py            # 读 signals/raw/hn_hiring_posts.json，evaluate
python3 signals/verify_hn_independent.py --fetch    # 重新从 HN API 抓两个线程（会覆盖缓存）
python3 signals/verify_hn_independent.py --prove-red # 三处注入，门必须变红
```

关联：`signals-baseline.md` 第 5 条口径缺陷（archetype 同源）末尾指向本报告作为正确解法。
