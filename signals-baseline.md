# 拐点信号基线（Signals Baseline）

> 基线日期：2026-11-16（数据快照 `signals/raw/enriched_a.json`，抓取于 2026-11-16/17）
> 目的：用**可复算的正文级测量**做纵向跟踪，判断 Agent Infra 方向是否从「岗位名」进入「标准要求清单」。单次快照不下行业级拐点结论；能下的是**方向性判断 + 判定阈值**。

本文件替换了第一版「1 家实采 + 11 家待实采」的手抄骨架。旧骨架的问题不是不认真，是**分母太小且样本是我预置的**：它只能证明「有人这么写过一行 JD」，不能证明「这类要求在多常见」。现在分母是 4017 条带正文的真实 JD。

---

## 0. 怎么读这份基线（口径先说清，否则数字会被误引）

| 术语 | 定义 | 为什么重要 |
|---|---|---|
| `title_rate` | 该轴词表命中**岗位标题**的比例 | 「这个岗被叫成这个名字」 |
| `body_rate` | 该轴词表命中**JD 正文**的比例 | 「这个岗实际要干这件事」 |
| `hidden_rate` | body − title | **能力被别的标题吸收**。高 hidden = 这是横切技能，不是独立岗位 |
| `required_rate` | API 自带的 `requirements[]` 中 `priority=required` 且命中该轴的比例 | 招聘方在**承诺条件**，不是列 nice-to-have |
| `preferred_rate` | 同上但 `priority=preferred` | 加分项 |
| `hard_soft` | required / preferred | 越高 = 越像硬门槛 |

四条必须随数字一起引用的口径缺陷（**不写这四条就不许引用数字**）：

1. **`harness` 的中文口径偏高**。中文 JD 里 `Harness` 常作**产品/团队名**（「千问办公-AI Agent Harness 工程师」「企业微信-AI Agent Harness 全栈工程师」），不是「agent loop 机制」。2026-11-16 加中文词表时 harness 从 26.1% 一度跳到 67.8%，逐词排查发现主因是 `skills?` 与裸 `harness` 两个词（`skills?` 命中 2345 条，其中绝大多数是 "communication skills / programming skills in Python"）。已移除这两个裸词，改为 `(agent|ai|model) harness` / `harness (engineering|architecture|kernel|runtime)` / `(agent|tool|ai) skills`。**现在的 27.6% 是修后的数，不是修前的 67.8%。** 但残余偏高仍在：中文样本里 harness 相关岗标题常直接写 Harness，正文不再重复机制词。
2. **中文侧单独建了一个切片**：主语料里中文 JD 只有 36 条（`enrichment.posting_language == 'zh'`）/ 56 条（`countries` 含 cn），用这个分母测中文正则等于测噪音。所以另建 `signals/fetch_zh.py`（中文查询 + `countries=['cn']` + 正文中文字符占比 ≥30% + 标题过滤），得到 **1379 条中文 JD 切片**（`signals/raw/enriched_zh.json`，cn 1366 / tw 9 / 其余 4）。**§4.2 是这份切片的读数，与主表 n=4017 不能混算**——两边分母不同、筛选条件不同，合并会得到一个既不是全球也不是中国市场的怪物。该切片仍不代表中国市场（来源仍是同一个 ATS 聚合站），只代表「这个站上能抓到的中文 JD」。**它的构成由查询集决定**：首轮 30 条查询只捞到 17.1% 平台岗，加入 `AI基础设施`/`模型服务`/`智能体平台` 后升到 39.0% —— 见 §4.2 的表。
3. **`q` 多词查询会退化，所以「每轴 8–11 条查询」的实际覆盖度低于字面**。实测 `q=agent` → 100830 条、`q=agent harness` → **同样 100830 条**、`q=harness` → 7459 条、`q=zzzqqqnomatch` → 0 条：这个端点把多词 `q` 折叠成首词（或首个有命中的词），不是短语匹配。所以 `fetch_freehire.py` 里 `"agent runtime"` / `"context engineering"` 这类查询在服务端实际是按 `agent` / `context` 检索的。后果有二：① `discovery.json` 里的 `matched_axis` 字段**不代表该 JD 真的属于那一轴**，本文件全文没有引用它；② 真正决定语料相关性的是 `classify.py` 的三档标题过滤与 `enrich_tier_a.py` 的排序，`q` 只负责「把候选池捞大」。这一条不影响规模（11638 条是去重后的真实岗位数），但**任何「我们按 X 轴检索了 N 条」的说法都不能成立**。
4. **年度对比不可用**。4017 条里 2026 年 3959 条、2025 年 44 条、更早 15 条。任何「同比去年」都是拿 44 条比 3959 条。本文件所有趋势**只在 2026-06 → 2026-11 的月内口径**下给。

另一个测量现实：`seniority` 在**顶层**字段里全部是 `None`（`signals/raw/enriched_a.json` 的 `seniority` / `category` / `ai_archetype` / `posting_language` / `min_years` / `salary_*` 非空数都是 0），但在 **`enrichment` 子对象**里是可用的：`enrichment.seniority` 1787/4017 有值（senior 1144 / lead 201 / staff 166 / principal 115 / middle 64 / intern 37 / c_level 30 / junior 30），`enrichment.category` 3922/4017 有值，`enrichment.posting_language` 有 3460 en / 36 zh / 44 fr / 43 de / 36 ja。**职级分层见 §4.1**；下面的主表与趋势仍用不分层的全量口径。

---

## 1. 语料（怎么来的、能代表谁）

采集管线（全部可复跑，代码在 `signals/`）：

```
fetch_freehire.py   72 条查询 × 3 页 × 100 条 → 11638 条唯一岗位（signals/raw/discovery.json）
classify.py         标题三档分类 + drop 原因可审计 → A 3845 / B 1627 / D 6166 → candidates 5472
enrich_tier_a.py    按 title_score 排序、PER_COMPANY_CAP 封顶、断点续抓 → 4017 条带正文
analyze_axes.py     8 轴正文级测量 + 自检 + 双向反证 → signals/raw/axes_report.json
```

来源是 freehire.me（约 50 个 ATS 平台归一化：ashby / greenhouse / workday / lever / smartrecruiters / 飞书 / 阿里 / 腾讯 / 美团 / mokahr / wellfound / ycombinator…）。这个来源决定了三条偏置：

- **公司偏置**：能进 ATS 的公司才在样本里。2997 家公司，最大单家 12 条（Databricks），PER_COMPANY_CAP=3 是富集阶段的封顶，所以**任何「某公司要求 X」的结论都只能引用单条 JD**。
- **地区偏置**：us 1057 / in 791 / gb 203 / sg / ca / de / nl / pl / au / it / es / cn 56。印度占比 19.7% 远高于直觉，这会系统性抬高「工具/MCP + 上下文」类要求的表面频率（印度外包与产品公司 JD 模板化程度高）。
- **时间偏置**：中位年龄 23 天，≤90 天占 84.1%。这是一份**当月快照**，不是历史档案。

### 1.1 `enrichment` 子对象里还有什么（覆盖率与可用/不可用）

同一份 `enriched_a.json` 的 `enrichment` 子对象里有 19 个键，覆盖率差别极大。**只有覆盖率高的才能进结论**：

| 字段 | 非空/4017 | 可用性 |
|---|---|---|
| `category` | 3922 | 可用（ai_engineering 1455 / devops 739 / software_engineering 481…） |
| `requirements[]` | 2328 | 可用，`required`/`preferred` 就来自这里（不是我们的语气猜测） |
| `posting_language` | 3772 | 可用（en 3460 / zh 36 / fr 44 / de 43 / ja 36） |
| `seniority` | 1787 | 可用，见 §4.1 |
| `company_type` | 1202 | **样本过窄**，见下 |
| `domains` | 1244 | 可用（ai 305 / other 157 / fintech 125 / devtools 56 / healthcare 55） |
| `employment_type` | 1482 | 可用（full_time 1140 / contract 249 / part_time 51 / internship 41） |
| `education_level` | 743 | 样本偏窄（bachelor 418 / master 229 / phd 95） |
| `salary_min/max/currency/period` | ~693–729 | 只有美元/年度与少量时薪，且 693 条里混着 80 这类日薪值，**不做薪资结论** |
| `english_level` | 165 | 太窄 |
| `company_size` | 363 | 太窄 |
| `visa_sponsorship` / `relocation` | 205 / 234 | 太窄 |
| **`experience_years_min`** | **2128** | **不可用于职级判断，见下** |

**`experience_years_min` 是一个「正文里最小年数」的抽取，不是岗位要求的年限。** 实测反例：`Sr. Manager, AI Engineer` 的 `experience_years_min=1`，而正文写的是「At least 4 years of developing AI and ML algorithms… At least 1 year of **people leadership** experience」；`Senior Software Engineer` 的 `=1` 来自「1 year of experience with software design and architecture」。按 `experience_years_min` 分组做轴率对比会得到「经验要求越低越要八轴」的假结论（实测 1 年组 mean_axes 2.78 vs 3 年组 2.13，**这是抽取伪影**）。**本基线不使用该字段做任何分层。**

`company_type` 也可以拿来做一次对照，但要先看分母：product 657 / startup 191 / outsource 137 / outstaff 100 / inhouse 100（合计 1185/4017）。实测 `outsource` 组的 harness 40.9% / context_memory 51.1% / tool_mcp 45.3% 都高于 `product` 组的 27.9/36.2/32.6 —— 但 `outsource` 只有 137 条且 25 条在印度，这与 §1「印度占比 19.7% 抬高工具/上下文」是同一个混淆，**不单独下结论**。

`skills` 字段可用（1484/4017 有值，855 个不同标签），top：`ai 3580 / python 2469 / llm 2448 / cloud 2130 / agentic-ai 1997 / api 1991 / observability 1655 / machine-learning 1591 / ci-cd 1448 / aws 1234 / kubernetes 1185 / rag 1081 / mcp 872`。注意这是**标签出现次数**（一条 JD 多个标签），不是 JD 条数。

---

## 2. 八轴读数（n=4017，`python3 signals/analyze_axes.py`）

| 轴 | title | body | hidden | required | preferred | hard/soft |
|---|---|---|---|---|---|---|
| `runtime` 执行引擎 | 0.4% | 8.7% | 8.3% | 1.0% | 1.0% | 0.98 |
| `harness` 框架与循环 | 1.8% | 27.6% | 25.8% | 8.2% | 5.4% | 1.52 |
| `context_memory` 上下文与记忆 | 3.8% | **42.6%** | 38.9% | **21.2%** | 7.8% | **2.70** |
| `tool_mcp` 工具/MCP | 1.2% | 34.2% | 33.0% | 13.0% | 7.2% | 1.81 |
| `sandbox_security` 沙箱/凭证/身份 | 1.6% | 29.1% | 27.5% | 6.6% | 4.1% | 1.63 |
| `control_plane` 网关与成本 | 0.5% | 8.6% | 8.1% | 1.2% | 1.7% | **0.70** |
| `eval_gate` 评测与门禁 | 0.7% | 22.1% | 21.4% | 4.1% | 3.8% | 1.09 |
| `observability` 可观测（AI 专项） | 0.9% | 21.3% | 20.4% | 4.4% | 3.8% | 1.15 |

**这张表最重要的一栏是 `hidden`，不是 `body`。** 八轴的 hidden/body 比值分别是 runtime 0.957 / harness 0.935 / context_memory 0.912 / tool_mcp 0.964 / sandbox_security 0.944 / control_plane 0.943 / eval_gate 0.968 / observability 0.959 ——**全部 ≥0.91**。意思是：这些能力几乎从不以它们自己的名字出现在岗位标题上，而是被塞进「Software Engineer / AI Engineer / Platform Engineer / SRE」。4017 条里 70.6%（2836 条）至少有一条轴是「正文有、标题无」。

由此得到的第一个判断：**Agent Infra 现在主要不是一组岗位名，而是一组被横向塞进通用工程岗的要求。** 找岗位的人看标题会漏掉绝大多数机会；招人的团队写标题时会以为自己在招通用工程师。

`hard_soft` 一列给出质地差别：`context_memory` 2.70（写得最硬——上下文/记忆是明确的门槛），`tool_mcp` 1.81，`sandbox_security` 1.63，`harness` 1.52；而 `control_plane` 0.70 与 `runtime` 0.98 —— **preferred 多于 required**，说明网关/成本/runtime 这类东西目前多数还在「加分」「了解即可」的位置，不是必须项。

---

## 3. 轴深度与共现（是清单，还是同一件事）

单条 JD 点亮的轴数（n=4017）：

| 轴数 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| 占比 | 25.3% | 24.0% | 17.1% | 14.7% | 8.4% | 6.2% | 2.8% | 1.1% | 0.3% |

即 **≥4 轴占 18.8%（757 条）**。这 757 条才是「一个人要同时管 runtime/tools/memory/eval」的那种岗。

共现抬升（`lift = p_both / (p_a * p_b)`，>1 = 不是各自独立）：

| 轴对 | both | lift |
|---|---|---|
| `harness` + `tool_mcp` | 698 | **1.84** |
| `context_memory` + `harness` | 765 | 1.62 |
| `sandbox_security` + `tool_mcp` | 641 | 1.60 |
| `context_memory` + `tool_mcp` | 933 | 1.59 |
| `harness` + `sandbox_security` | 493 | 1.53 |
| `context_memory` + `eval_gate` | 506 | 1.34 |

全部 28 个轴对里，**27 个 lift >1.3，最低一对是 `runtime` + `context_memory` = 1.261**（187 条）——仍然 >1，说明八轴在正文里从未互相独立，只是 runtime 与上下文的相关性略弱于其余组合。所以「8 类标签」不是一张勾选清单，是一件事的几个侧面：要工具调用（MCP）就必然要上下文管理，要上下文就必然要 loop，要 loop 就必然要沙箱与权限，要沙箱就必然要可观测，要可观测就必然要评测闭环。

这条对求职者的直接含义：**按轴逐个补技能是低效路径**；按「一个能跑起来的最小闭环」补（loop + tool + context + trace + eval）才匹配 JD 的实际形状。

---

## 4. 标题队列与地区（谁在被要求更多）

标题队列（`agent_named` = 标题含 agent/agentic；`llm_named` = 含 llm/ai engineer/genai；`platform_named` = 含 platform/infrastructure/sre/reliability/devops）：

| 队列 | n | mean_axes | 前四轴 |
|---|---|---|---|
| `agent_named` | 1093 | **2.73** | tool_mcp 54.8% / context_memory 54.4% / harness 52.0% / sandbox_security 34.1% |
| `llm_named` | 1415 | 2.57 | context_memory 70.4% / tool_mcp 48.0% / harness 38.4% / sandbox_security 34.5% |
| `platform_named` | 1621 | **1.41** | context_memory 23.4% / observability 23.1% / sandbox_security 22.3% / tool_mcp 21.1% |

`agent_named` 的平均轴数接近 `platform_named` 的两倍。**「轴名化岗位」确实要求更多轴**——不是所有 infra 岗都这样。`agent_named` 里 ≥4 轴占 31.8%（348/1093）。

地区（同口径，n 已标注；中文侧样本小，见 §0）：

| 轴 | cn (56) | us (1057) | in (791) | gb (203) |
|---|---|---|---|---|
| runtime | 23.2% | 14.2% | 7.8% | 8.9% |
| harness | 32.1% | 30.1% | 39.8% | 27.6% |
| context_memory | 44.6% | 36.0% | **69.2%** | 28.6% |
| tool_mcp | 42.9% | 32.9% | 45.9% | 25.1% |
| sandbox_security | 32.1% | 30.6% | 35.9% | 30.0% |
| control_plane | 19.6% | 11.4% | 9.6% | 8.4% |
| eval_gate | 25.0% | **30.2%** | 25.0% | 23.6% |
| observability | **46.4%** | 23.1% | 26.0% | 19.2% |

三个能说的：① 印度样本（791 条，19.7%）把 context_memory 与 tool_mcp 抬得异常高（69.2% / 45.9%），是模板化 JD 的痕迹，**引用整体数字时必须知道这一块占了近两成**；② 中国样本 runtime / control_plane / observability 三项最高，说明中文 JD 更偏「跑起来 + 看得见 + 管得住」；③ 美国样本 eval_gate 最高（30.2%），与「美国产品公司把评测当发布流程一部分」一致。

### 4.1 职级分层（`enrichment.seniority`，1787 条有值）

| 职级 | n | runtime | harness | context_mem | tool_mcp | sandbox_sec | control_plane | eval_gate | observability |
|---|---|---|---|---|---|---|---|---|---|
| intern | 37 | 8.1% | 18.9% | 51.3% | 32.4% | 24.3% | 2.7% | 27.0% | 2.7% |
| junior | 30 | 6.7% | 16.7% | 16.7% | 20.0% | 6.7% | 3.3% | 0.0% | 10.0% |
| c_level | 30 | 16.7% | 23.3% | 36.7% | 26.7% | 26.7% | 6.7% | 20.0% | 16.7% |
| middle | 64 | 9.4% | 34.4% | **51.6%** | 40.6% | 28.1% | 9.4% | 25.0% | 25.0% |
| principal | 115 | 12.2% | 28.7% | 41.7% | 34.8% | **37.4%** | **17.4%** | 26.1% | 22.6% |
| staff | 166 | 14.5% | 36.8% | 35.5% | **41.6%** | 34.3% | **16.3%** | **29.5%** | **31.9%** |
| lead | 201 | 8.0% | 36.3% | **52.2%** | 41.3% | 36.8% | 11.4% | 26.4% | 19.4% |
| senior | 1144 | 9.0% | 29.0% | 41.6% | 35.9% | 30.9% | 7.9% | 24.0% | 24.5% |

表按 n 从小到大排列（`python3 signals/analyze_axes.py` 会直接打出这张表）。三件事：① `control_plane` 几乎只在 staff（16.3%）与 principal（17.4%）出现，senior 只有 7.9%、junior 3.3% —— **网关/成本/配额是「到了 staff 才交给你」的东西**，与 §6 把它判成「尚未成为要求」一致；② `sandbox_security` 随职级单调上行（junior 6.7% → senior 30.9% → principal 37.4%）；③ `junior` 只有 30 条，**不能当结论**，只是提示低职级 JD 里八轴几乎都不出现。intern 的 context_memory 51.4% 是 37 条的小样本噪音（实习岗 JD 常整段抄平台介绍）。

### 4.2 中文切片（n=1379，`signals/raw/enriched_zh.json`）

| 轴 | title | body | hidden | required | preferred | hard/soft |
|---|---|---|---|---|---|---|
| runtime | 0.1% | 6.3% | 6.2% | 2 | 6 | 0.33 |
| harness | 1.1% | 10.6% | 9.5% | 28 | 10 | 2.80 |
| context_memory | 0.3% | 35.0% | 34.7% | 49 | 14 | 3.50 |
| tool_mcp | 0.0% | **33.5%** | 33.5% | 43 | 4 | **10.75** |
| sandbox_security | 0.2% | 18.4% | 18.1% | 6 | 4 | 1.50 |
| control_plane | 0.3% | 13.3% | 13.0% | 2 | 2 | 1.00 |
| eval_gate | 0.0% | 21.5% | 21.5% | 6 | 9 | **0.67** |
| observability | 0.4% | 32.4% | 32.0% | 7 | 4 | 1.75 |

与主表（英文为主，n=4017）的结构差异：

- **`harness` 只有 10.6%，而主表 27.6%。** 这是 §0 缺陷 1 的反向证据：`Harness` 在中文语料里多是产品/团队名，而不是「agent loop 机制」。主表那个 27.6% 主要来自英文 JD 的 `agent loop / agent framework / agent scaffold` 表述，不是中文「Harness 工程师」这个标题。
- **`tool_mcp` 的 hard/soft 是 10.75**（required 43 / preferred 4），主表 1.81。中文 JD 一旦提工具/MCP，几乎全写在必须段。这是本文件里最硬的一条中文侧读数。
- **`eval_gate` 21.5% 但 hard/soft 只有 0.67**（preferred 9 > required 6）——中文侧提评测比英文多、但更少把它写成任职要求。与主表把 eval_gate 判「加分」一致，中文侧更极端。
- **`context_memory` 35.0% vs 主表 42.6%**：中文侧更低。主表这个数被印度样本抬高（§4 的 in 69.2%），中文切片不含印度，所以更接近「不带模板化倾向」的读数。**这也提示主表的 42.6% 可能偏高。**
- `control_plane` 13.3%（主表 8.6%）：中文切片的查询里含「AI 基础设施 / 模型服务 / 平台架构」，会带进更多平台岗，见下条。

**标题构成变了，而且是被查询集决定的**：

| 查询集 | n | platform/infra | algo/research | app/dev |
|---|---|---|---|---|
| 首轮（智能体/大模型 为主，30 条查询，预算 400） | 469 | **17.1%** | 37.7% | 25.2% |
| 扩到 1379 条（加「AI基础设施 / 模型服务 / 智能体平台 / Agent平台 / AI平台 / AI应用」） | 1379 | **39.0%** | 24.7% | 24.6% |

第一轮 17.1% 那个数**不是中文 JD 的属性，是我的查询集的属性**：`智能体` 与 `大模型` 是覆盖最广的两个词，它们把算法岗与应用岗全捞进来了；而 `AI基础设施`/`模型服务`/`智能体平台` 直接指向平台岗。**教训（接 §0 缺陷 3）：查询集决定语料构成，任何「中文侧只有 X% 是平台岗」的结论必须先公布查询集，否则是在描述自己的检索词。**

`fresh` vs `stale`（≤90d n=459 vs >365d n=218，同一匹配器）：`tool_mcp` 41.4% → 22.5%、`observability` 39.4% → 22.9%、`sandbox_security` 24.6% → 7.8%、`eval_gate` 27.9% → 13.8%、`control_plane` 18.1% → 8.3%。**八轴在中文侧全部是「新 JD 有、老 JD 没有」**，方向一致。注意 stale 只有 218 条，且中文招聘站的老岗常是未清理的陈旧挂单，这条只能当方向提示。

复跑：`python3 signals/fetch_zh.py 900 3`（预算 900 条 / 每查询 3 页），输出 `signals/raw/enriched_zh.json`；出表 `python3 signals/analyze_axes.py --globs 'enriched_zh.json' --out signals/raw/axes_report_zh.json`。

### 4.3 标题家族交叉（AI 名 × 平台名，最反直觉的一张表）

上面的 `cohorts` 是三个重叠的正则队列，回答的是「轴名化岗位要不要更多轴」。真正该问的是**「是 AI 这个字带来的轴，还是 platform 这个字带来的」**——因为 platform / infra / SRE 标题看起来最像这份基线的目标读者。把两个独立的正则交叉（英文 + 中文双语的 `TITLE_AI` / `TITLE_PLATFORM`）：

| 家族 | n | 占比 | runtime | harness | context_mem | tool_mcp | sandbox_sec | control_pl | eval_gate | observability | mean |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ai_and_platform` | 454 | 11.3% | 21.4% | 38.8% | 44.9% | 42.1% | 32.2% | 12.8% | 21.6% | 23.4% | 2.37 |
| `ai_only` | 1722 | 42.9% | 8.8% | 41.8% | **65.5%** | 49.9% | 33.2% | 7.6% | 27.5% | 21.7% | **2.56** |
| `platform_only` | 1363 | 33.9% | 5.9% | **11.9%** | **18.8%** | **16.1%** | 20.5% | 9.2% | 14.9% | 22.2% | **1.20** |
| `neither` | 478 | 11.9% | 4.2% | 10.5% | 26.2% | 21.8% | 35.8% | 6.5% | 23.6% | 15.1% | 1.44 |

**这张表的结论与「Agent Infra 是一组平台岗」的直觉相反**：

- `platform_only`（SRE / Infrastructure Engineer / Architect，1363 条）的 `context_memory` 只有 **18.8%**、`tool_mcp` 16.1%、`harness` 11.9%，八轴均值 **1.20** —— 四个家族里最低。
- `ai_only`（Agent Engineer / LLM Engineer，1722 条）均值 **2.56**，`context_memory` 65.5%、`tool_mcp` 49.9% —— 最高。
- 两者都中（454 条，11.3%）均值 2.37，介于中间。

**那八个轴不是「基础设施岗的升级版」，是「AI 岗的基础设施侧」。** 一个只挂 platform/infra 标题、正文不提 agent 的 JD，实际测不到这些轴。这也解释了 §4 的 `platform_named` mean_axes 1.41 —— 不是「平台岗要求少」，是**平台岗根本不谈这些**。

剔除印度后（n=3234）重算，结论不变、幅度收窄：`platform_only` 1.20 → **1.13**（context_memory 16.7%）、`ai_only` 2.56 → **2.40**（57.7%）、`ai_and_platform` 2.37 → 2.27（41.0%）。家族差异不是印度样本造成的。

中文切片（n=1379）同口径：`ai_and_platform` n=178（12.9%）均值 **2.57**（observability 44.9% / context_memory 51.7%）、`ai_only` n=778（56.4%）1.68、`platform_only` n=311（22.6%）1.36（control_plane 21.5% 是四家族最高）、`neither` 112 条 1.50。**中文侧 `ai_only` 反而比 `ai_and_platform` 低 0.89**，与英文侧方向相反——中文「大模型应用算法」这类标题里 harness/tool_mcp 几乎不出现（10.4% / 38.0%），而「智能体平台」才带上它们。

**这一节的两条口径教训**：

1. **标题分类器必须双语**：英文-only 的 `TITLE_AI`/`TITLE_PLATFORM` 在中文切片上把 **64.2%（886/1379）**判成 `neither`。这跟轴词表最初纯英文时「中文侧整块漏测」是同一个错误，只是换了一层。现在 `title_family_selftest()` 用 7 条中英混合标题做断言，`prove_red` 第 3 处注入把正则换回英文-only → 必须变红。
2. **`\bai\b` 不能进 `TITLE_AI`**：加上它以后 `ai_and_platform` 从 454 条膨胀到 1419 条（35.3%），均值从 2.37 掉到 1.70 —— 因为 "AI Data Engineer" / "GenAI-Driven Data Platforms" 是数据岗不是 AI agent 岗。**召回涨 3 倍、精度崩掉 4 成，等于把「AI 岗」换成「提到 AI 的岗」。**

复跑：`python3 signals/analyze_axes.py`（表在 `title families` 段）；中文切片加 `--globs 'enriched_zh.json'`。

---

## 5. 趋势（只在 2026-06 → 2026-11 月内口径）

全量口径（每月 n≥50）：

| 轴 | 26-06 | 26-07 | 26-08 | 26-09 | 26-10 | 26-11 | Δ |
|---|---|---|---|---|---|---|---|
| tool_mcp | 23.2% | 32.6% | 33.4% | 34.0% | 35.1% | 35.6% | **+12.4pp** |
| context_memory | 34.7% | 47.4% | 50.0% | 48.6% | 44.3% | 40.0% | +5.2pp |
| sandbox_security | 24.2% | 29.1% | 33.7% | 32.9% | 31.0% | 26.4% | +2.2pp |
| runtime | 6.3% | 10.9% | 13.5% | 10.2% | 8.4% | 7.1% | +0.8pp |
| harness | 26.3% | 31.4% | 34.7% | 34.7% | 26.5% | 24.8% | −1.5pp |
| control_plane | 9.5% | 7.4% | 10.1% | 10.7% | 9.3% | 7.3% | −2.1pp |
| observability | 21.1% | 26.9% | 21.8% | 25.5% | 22.7% | 18.1% | −3.0pp |
| eval_gate | 23.2% | 26.9% | 23.9% | 24.8% | 23.7% | 18.7% | −4.5pp |

**受控口径**（tier A 且标题含 agent/agentic/llm/ai engineer，n=1310，每月 ≥40）：这条最重要，因为它把「语料构成漂移」压住——全量口径从 6 月到 11 月，印度占比从 34.3% 掉到 16.5%、tier A 占比从 88% 掉到 71.6%，这会自己制造趋势。

| 轴 | 26-06 | 26-07 | 26-08 | 26-09 | 26-10 | 26-11 | Δ |
|---|---|---|---|---|---|---|---|
| tool_mcp | 39.1% | 43.3% | 48.4% | 50.9% | 49.5% | **52.8%** | **+13.7pp** |
| runtime | 8.7% | 20.9% | 25.3% | 16.4% | 13.8% | 13.3% | +4.6pp |
| sandbox_security | 30.4% | 29.9% | 31.6% | 39.4% | 32.7% | 30.1% | −0.3pp |
| observability | 21.7% | 29.9% | 27.4% | 30.9% | 22.6% | 19.0% | −2.7pp |
| harness | 45.7% | 47.8% | 57.9% | 58.2% | 40.2% | 41.3% | −4.4pp |
| control_plane | 13.0% | 7.5% | 11.6% | 10.9% | 9.5% | 6.6% | −6.5pp |
| context_memory | 58.7% | 61.2% | 61.1% | 66.7% | 52.8% | 51.1% | −7.6pp |
| eval_gate | 32.6% | 29.9% | 27.4% | 31.5% | 28.1% | 23.4% | −9.2pp |

**两个口径下都单调上行的只有一个轴：`tool_mcp`**（全量 +12.4pp，受控 +13.7pp，且 26-10→26-11 逆势上涨）。其余多数在全量涨、受控跌 —— 那是语料构成漂移，不是真实风向。

**第三个口径：剔除印度（n=3226，去掉 791 条 in）**。这一列存在的理由不是「印度不好」，而是 §1 已说明印度占 19.7% 且 JD 模板化程度高，会自己制造趋势。同一匹配器下的轴率变化：

| 轴 | 全量 4017 | in 791 | 剔除印度 3226 | Δ（剔印 − 全量） |
|---|---|---|---|---|
| runtime | 8.7% | 7.8% | 8.9% | +0.2pp |
| harness | 27.6% | 39.8% | 24.6% | **−3.0pp** |
| context_memory | 42.6% | 69.2% | **36.1%** | **−6.5pp** |
| tool_mcp | 34.2% | 45.9% | 31.3% | **−2.9pp** |
| sandbox_security | 29.1% | 35.9% | 27.4% | −1.7pp |
| control_plane | 8.6% | 9.6% | 8.4% | −0.2pp |
| eval_gate | 22.1% | 25.0% | 21.4% | −0.7pp |
| observability | 21.3% | 26.0% | 20.1% | −1.2pp |

**结论：主表的 `context_memory 42.6%` 里有 6.5pp 是印度样本撑起来的，剔除后是 36.1%。** `harness` 与 `tool_mcp` 各被抬高约 3pp。其余四轴几乎不动。所以引用这些数字时，正确说法是「context_memory ≈ 36–43% 取决于是否含印度模板化 JD」，而不是一个精确的 42.6%。

再叠一层受控（剔除印度 + tier A + 标题含 agent/agentic/llm/ai engineer，n=1011，每月 ≥30 条）：

| 轴 | 26-06 | 26-07 | 26-08 | 26-09 | 26-10 | 26-11 | Δ |
|---|---|---|---|---|---|---|---|
| runtime | 11.8% | 25.6% | 31.7% | 19.4% | 12.3% | 13.7% | +2.0pp |
| harness | 52.9% | 46.2% | 52.4% | 44.4% | 37.7% | 39.1% | **−13.9pp** |
| context_memory | 47.1% | 48.7% | 54.0% | 57.4% | 46.9% | 43.9% | −3.1pp |
| tool_mcp | 41.2% | 41.0% | 50.8% | 45.4% | 46.5% | **49.9%** | **+8.7pp** |
| sandbox_security | 32.4% | 33.3% | 34.9% | 37.0% | 28.6% | 29.4% | −3.0pp |
| control_plane | 14.7% | 10.3% | 14.3% | 12.0% | 8.2% | 7.3% | −7.4pp |
| eval_gate | 26.5% | 30.8% | 30.2% | 29.6% | 25.2% | 21.8% | −4.6pp |
| observability | 26.5% | 28.2% | 27.0% | 29.6% | 21.1% | 18.1% | −8.4pp |

`tool_mcp` 在**三个口径**下都是唯一持续上行的轴（全量 +12.4pp / 受控 +13.7pp / 剔印受控 **+8.7pp**）。`harness` 在剔印受控下是 −13.9pp（比此前看的 −4.4pp 更陡），说明它的下滑主要发生在非印度样本里，而不是印度样本拉高了均值。

topic 侧同时看到 `mcp_word` 从 14.7% → 24.1%（+9.4pp），`MCP` 作为 requirement 的优先级 split 是 required 221 / preferred 248。

**能下的结论（严格在这个窗口内）**：工具/协议化（Tool / MCP）是过去半年唯一**同时**在「全量」与「受控」两个口径下都持续上行的要求；上下文/记忆在 8–9 月冲顶后回落；评测门禁在同期持续走低。

---

## 6. 判定：哪些是门槛、哪些是加分、哪些还没成为要求

| 档 | 轴 | 依据 |
|---|---|---|
| **硬门槛**（required 率高 + hard/soft 高） | `context_memory`、`tool_mcp` | required 21.2% / 13.0%，hard_soft 2.70 / 1.81，body 42.6% / 34.2% |
| **准门槛**（body 高但 required 中等） | `sandbox_security`、`harness` | body 29.1% / 27.6%，required 6.6% / 8.2%，hard_soft 1.63 / 1.52 |
| **加分/了解即可**（hard_soft ≤1.15） | `eval_gate`、`observability` | required≈preferred，且 eval_gate 月内 −9.2pp |
| **尚未成为要求**（preferred > required） | `control_plane`、`runtime` | hard_soft 0.70 / 0.98，body 仅 8.6% / 8.7%，标题率 0.5% / 0.4% |

这张表跟 2026 校招 JD 截图（小红书 RAI Studio，8 项全列「必须」）给出的画像是**同一方向、不同成熟度**：校招岗把整个体系一次性写成必须，市场存量 JD 里只有 context/tool 到了硬门槛，runtime/control_plane 还停在「加分」。

这正是「校招 JD 前瞻性偏高」的量化证据：一个 2027 校招岗列 8 个必须项，而同期 4017 条社招 JD 里 8 轴全中的只有 0.3%（13 条）。

**§4.3 给这张表加了一条限定**：上面四档的 body 率是全量口径，含 33.9% 的 `platform_only` 标题。把家族拆开看，硬门槛那两个轴（`context_memory` 65.5%、`tool_mcp` 49.9%）只在 `ai_only` 家族成立；在 `platform_only` 家族是 18.8% / 16.1%。**所以「硬门槛」不是对「所有 infra 岗」成立，是对「AI 岗」成立。** 引用这张表时必须带上这一句，否则会把一个岗位族的读数当成全行业读数。

---

## 7. 固定样本表（24 家，逐条可点开）

下面是语料里 ≥3 轴的真实 JD，作为后续季度对比的**固定锚点**。每条都是 `signals/raw/enriched_a.json` 里的记录，链接带 `utm_source=freehire.me` 是来源聚合标记。

| # | 公司 | 岗位 | 轴数 | 发布 |
|---|---|---|---|---|
| 1 | Astoria AI | Founding AI Research Engineer: Agent Harness & Model Systems | 8 | 2026-10-20 |
| 2 | ImagineArt | Agent Infrastructure Engineer — Core Harness (Superagent) | 7 | 2026-08-18 |
| 3 | datasite | Staff Software Engineer, AI Agent Platform & Runtime | 7 | 2026-10-27 |
| 4 | Tencent（腾讯） | 企业微信-AI Agent Harness 全栈工程师 | 7 | 2026-10-08 |
| 5 | Geico | Senior Software Engineer, AI Agent Platform | 7 | 2026-09-30 |
| 6 | MeridianLink | AI Engineer – Trust & Explainability (AI Platform) | 6 | 2026-09-28 |
| 7 | Netflix | Software Engineer 5 – Agent Platform, AI Platform | 6 | 2026-06-09 |
| 8 | Atlan | Principal Software Engineer - Agent & App Platform | 6 | 2026-10-30 |
| 9 | BigCommerce | Senior Backend Engineer (AI Agent) | 6 | 2026-10-21 |
| 10 | WuXi Biologics | Agentic AI Engineer | 6 | 2026-11-09 |
| 11 | MiniMax | Agent Sandbox 系统架构师 | 6 | 2026-05-28 |
| 12 | Alibaba Group（阿里） | 千问办公-AI Agent Harness 工程师 | 5 | 2026-11-15 |
| 13 | Amazon | Software Development Engineer - AgentCore, AWS Agentic AI | 5 | 2026-11-02 |
| 14 | Perplexity AI | Member of Technical Staff (Software Engineer, Enterprise) | 5 | 2026-11-01 |
| 15 | Accenture | AI Infrastructure Architect | 5 | 2026-07-30 |
| 16 | Bank of America | Principal Engineer - Context Engineering & LLM Optimization | 5 | 2026-06-29 |
| 17 | 曦望 Sunrise | Agent Infra 专家 | 5 | 2026-03-17 |
| 18 | Dynamo AI | Senior Full Stack Engineer, Agentic Security | 4 | 2026-11-17 |
| 19 | Thomson Reuters | Staff Software Engineer, Search Retrieval Platform | 4 | 2026-11-05 |
| 20 | Meituan（美团） | Agent Harness 工程师 | 4 | 2026-08-06 |
| 21 | ARM | SRE, Staff AI Infrastructure Engineer | 4 | 2026-09-17 |
| 22 | ByteDance（字节） | Harness/Runtime 架构师（小花项目） | 4 | 2021-04-19 |
| 23 | LPL Financial | AVP, Agentic Platform Controls, Non-Human Identity & AI Security | 3 | 2026-08-18 |
| 24 | 小红书 RAI Studio | 2027 校招 AI Agent Infra 工程师（用户提供截图，不在语料内） | 8（全「必须」） | 2026-11-16 |

URL 全部落在 `signals/raw/sample_20.json`（该文件实际含 36 条 ≥3 轴的记录，上表从中挑 24 条；查看全部：`python3 -c "import json;[print(o['company'],o['n_axes'],o['url']) for o in json.load(open('signals/raw/sample_20.json'))]"`）。第 22 条发布时间 2021-04-19 是 ATS 里的旧记录，**不能当 2026 的当前岗位**，列在这里只是因为它是「Harness/Runtime 架构师」这个中文标题的原始出处；§5 的趋势统计已把它排除在月内口径外。

---

## 8. 引用句（可直接用于报告，全部来自正文）

- **context/memory 是硬门槛的写法**：Bank of America「Principal Engineer - Context Engineering & LLM Optimization」；Databricks「8+ years SWE, with at least 2 years building production LLM or agentic applications (agents, RAG pipelines, tool-use, multi-agent orchestration)」。
- **tool/MCP 从「了解」变「会用」**：Dynamo AI「Understanding of Model Context Protocol (MCP), have built MCP servers/clients, and understand how LLMs invoke tools」；Netflix「working fluency with modern agent frameworks and the tool/function-calling and MCP patterns they share — deep enough to have an opinion about where they help and where they get in the way」；Luxoft「Experience building and running MCP servers and tools」。
- **runtime 的具体形状（长任务 + 断点）**：Truewind「Building orchestration for long-running agent workflows, including queues, retries, cancellations, checkpoints, resumability, and failure recovery」；datasite「resilient agent orchestration: asynchronous tasks, specialized subagents, delegation, checkpoints, resumability, retries, failure recovery, and human approvals」。
- **eval 门禁的真实词汇**：Databricks「evaluation flywheel… offline evals (nDCG, MRR, Recall@K, Precision@K), LLM-as-judge harnesses, human-in-the-loop labeling, and online experimentation」；Thomson Reuters「offline evaluation, search grading, LLM-as-judge scoring, and online experiments, so every change to retrieval can be measured」。
- **安全与身份**：01.tech「Implement LLM guardrails to prevent prompt injection, protect personally identifiable information (PII)…」；Databricks「Understanding of LLM failure modes: hallucination, incorrect tool use, ambiguous intent, prompt injection, excessive permissions」；LPL Financial「owns the enterprise control plane for agentic technologies」。
- **中文侧写得最细的一条**（腾讯企业微信）：「AgentLoop（推理-行动循环）、工具编排、指令调度、运行环境；Context Engineering：多轮对话上下文压缩、Skill 体系、跨会话 Long-term Memory、知识检索、长任务状态快照与恢复、token efficiency；执行轨迹回放、上下文编排器、工具注册中心、评测数据管理后台」。
- **中文侧把 sandbox 当资源层**（MiniMax）：「覆盖浏览器自动化环境、容器运行环境、K8s 托管的容器集群、虚拟机环境、物理机集群… 统一的环境初始化、任务派发、生命周期管理、资源限额、状态回收、故障隔离和审计；凭证注入与回收、不可信代码执行防护、逃逸风险防护」。

---

## 9. 判定记录与下一期阈值

**2026-Q4（本期）** —— 结论：**方向成立，尚未到行业级拐点**。

- 成立的部分：8 轴里有 6 轴的 body_rate >20%，且互相 lift ≥1.3，说明这套能力在真实 JD 里是**成组出现**的；`tool_mcp` 在两个口径下都持续上行（受控 +13.7pp），是最硬的风向证据。
- 不成立的部分：`runtime` / `control_plane` 的 hard_soft <1（preferred 多于 required），8 轴全中只占 0.3%；语料是单平台单月快照，无年度对比；`seniority` 缺失；中文样本 36 条。
- 因此**不判「行业级拐点」**。能判的是「横向要求扩散」：能力进入了通用岗的正文，但还没进入通用岗的标题与硬性条件。

**下一期（2026-Q1 / 2027-02）判定阈值**（先写死，避免事后调）：

| 目标 | 通过条件 | 不过就说明 |
|---|---|---|
| 拐点确认 | 受控口径下 `tool_mcp` ≥60% 且 `runtime` 的 hard_soft ≥1.2 | 仍是「加分」阶段 |
| 岗位化确认 | `context_memory` 的 title_rate ≥8%（现 3.8%） | 能力还躲在通用标题里 |
| 生态确认 | `mcp_word` ≥35%（现 21.9%）且 required ≥ preferred 2 倍（现 221/248，未达） | MCP 仍偏「了解」 |
| 测量确认 | 中文切片 ≥800 条且 platform/infra 标题 ≥150 条 —— **已达成（1379 / 538）** | — |
| ~~职级覆盖 ≥80%~~ | **已证不可通过重抓达成，见下** | — |

**关于「把 `enrichment.seniority` 覆盖率从 44.5% 提到 80%」这条阈值：测过了，撤掉。** 我抽查 3 条 `enrichment_version=0` 且无 seniority 的记录，用 `https://freehire.me/api/v1/jobs/<slug>` 重抓，返回的仍是 `enrichment_version=0` 且 `seniority` 仍为 `null` —— 服务端返回的是**它已缓存的 enrichment**，不是重新抽取。也就是说这个字段的覆盖度是上游抽取的属性，与「我们抓了多少条」无关。按 `source` 分组也看不到可修的系统性缺口（ashby 38.8% / greenhouse 60.9% / workday 54.0% / hirist 38.3% / jobleads 45.7%），差异来自 JD 正文本身有没有写职级词，而不是某个平台不给。**结论：44.5% 是这份语料的天花板，职级结论只能落在 1787 条有值的样本上，且必须随数字声明这个分母。**

**复跑命令**（任何人可复算本期所有数字）：

```bash
cd agent-infra-kickstart
python3 signals/fetch_freehire.py                          # 11638 条
python3 signals/classify.py                                # A3845/B1627/D6166
ENRICH_BUDGET=4200 PER_COMPANY_CAP=3 python3 signals/enrich_tier_a.py   # 4017 条
python3 signals/analyze_axes.py --selftest                 # 词表自检
python3 signals/analyze_axes.py --prove-red                # 自检双向可失败
python3 signals/analyze_axes.py                            # 出表
```

`--prove-red` 的输出必须是 `prove_red: OK, selftest is falsifiable under all 4 injected violations`。四处注入各自对应这个仪器真实犯过的错：

1. 词表换成 `§NOMATCH§` → 正样本自检必须变红（证明「词表根本没匹配」不是静默通过）。
2. 词表换成 `.` → 特异性自检必须变红（证明「一个词点亮八轴」不会被当成正常）。
3. **把标题家族正则换回英文-only** → `family selftest` 必须变红（中文标题被判成 `neither`）。对应 §4.3 教训 1。
4. **把 `seniority_of` 改成读顶层 `seniority` 字段** → 职级表必须变空、且 `seniority selftest` 必须变红。对应「我先写了本基线不含职级分层，隔一轮才发现 `enrichment.seniority` 有 1787 条」。**「拿不到数据」这个结论必须能被机器要求出示读的是哪个键 / 覆盖哪种语言。**

这条是整份基线的「尺子校准」——没有它，上面所有数字只是某个正则当时匹配到了什么。
