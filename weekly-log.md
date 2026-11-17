# Weekly Log（周节奏与证据留存）

> 规则：每周固定产出并留证据（代码提交/运行日志/评测报告/看板快照）。结项写“做了什么、证据在哪、下周做什么”。

## Week 0 — 2026-11-16（启动）
**目标**：完成范围定义、W1 最小闭环、可观测与评测门禁雏形。
- [x] 创建 kickstart 文档：`README.md` / `project-spec.md` / `signals-baseline.md` / `weekly-log.md`
- [x] 场景与工具定稿（写入 `project-spec.md` 第 1、6 节）：本地输入分析 4 步流程，4 个工具
- [x] W1 最小闭环：`Session/Step/Event` 状态模型 + 事件流 + Trace + 本地持久化 + 跳过已成功步骤的恢复执行
- [x] 幂等：`write_text` 同内容二次写入返回 `written=false / idempotent=true`
- [x] 路径逃逸防护：`../escape.md` → `error_code=PATH_ESCAPE`
- [x] 评测门禁：4 用例全绿（happy / resume / fail-fast / missing-dir）
- [x] 红证：`eval/prove_red.py` 注入违规后 `run_eval` 退出 1
- [x] 信号基线骨架：12 家样本位（1 家已实采 + 11 家待实采，标签注明“待核验”防编造）

**证据（命令 + 产物）**
```bash
cd agent-infra-kickstart
python3 -m agent.main run --topic "Agent Infra" --input-dir sample_input
#  → status=succeeded，产出 runs/<sid>/report.md / state.json / trace.jsonl
python3 eval/run_eval.py        # → passed 4 / 4, exit 0
python3 eval/prove_red.py       # → baseline exit=0, injected exit=1, OK
```
- 成功样例：`runs/sess_5a198909/report.md`（3 文件、8 关键词、per-file 统计）
- 中断恢复样例：`runs/sess_5182a8a2/`（`write_report` 注入失败 → `interrupted` → `resume` → `succeeded`，`list_inputs`/`extract_info` 未重跑）

## Week 0.5 — 2026-11-16（可靠性深化：超时 + 评测集扩到 21 条 + 接真实语料）
**目标**：把「可中断可恢复」从写字面变成有超时、有重试、有失败分级的真机制；把评测集从 4 条扩到 21 条并接真实语料。

- [x] 步骤级超时预算：`Step.timeout_ms` + 协作式 deadline（`agent/tools.py` 的 `set_deadline`/`_tick`），在 rglob 与分词内层循环里每 200 次迭代查一次钟
- [x] 失败分级：`RETRYABLE_ERROR_CODES`（TIMEOUT/EXCEPTION/LIST_ERROR/EXTRACT_ERROR/WRITE_ERROR/SUMMARIZE_ERROR）→ `interrupted`（剩余步骤留 pending 可续跑）；`BAD_INPUT`/`NOT_FOUND`/`PATH_ESCAPE` → 直接 `failed`
- [x] 完成态 resume 变 no-op：修掉「resume 已完成的会话会再追加一条 `session.succeeded`」
- [x] Trace 增加 `out_chars`/`out_items` 输出体积与 `attempt` 重试序号
- [x] 真实语料：`corpus/notes/`（从本工作区 `notes/` 复制的 4 篇真实笔记，41 KB，含中文与代码块）
- [x] 边界语料：`corpus/edge/`（空文件 / 非 UTF-8 / 单行 / 20k 行 689 KB / 嵌套目录）、`mixed/`、`truly_empty/`、`one_file/`、`binary/`
- [x] 评测集 4 → **21 条**（14 会话级 + 7 工具级；Week 0.6 再扩到 25 条），逐条覆盖表见 `eval/COVERAGE.md`
- [x] 红证从 1 处注入扩到 **3 处**（删 report per-file 段 / 删 deadline 守卫 / 删 resume no-op 守卫），每处都必须 exit≠0
- [x] 断言分层：状态（prefix_integrity、pending_preserved_for_resume）、Trace（JSONL 可解析、覆盖所有尝试、错误历史不被覆盖、不许替 state 撒谎）、事件（单终态事件）、产出（中断时必须能断言 `report_absent`）
- [x] 生成物不入库：`corpus/edge/large.txt` 由 `corpus/make_edge.py` 重建，`run_eval.py` 发现缺失会自动重建

**证据（命令 + 输出）**
```bash
python3 eval/run_eval.py        # → total 21, passed 21, exit 0
python3 eval/prove_red.py       # → baseline 0；三处注入各 exit 1；"OK"
python3 -m agent.main run --topic "agent reliability" --input-dir corpus/notes
#  → sess_056e8671 succeeded；report 4 文件；top keys: py=226 / volatile_artifact=204 / 随机=203
python3 -m agent.main run --topic "agent" --input-dir corpus/edge --timeout-ms 1 --max-retries 1
#  → sess_44088b8e interrupted（list_inputs TIMEOUT×2）
python3 -m agent.main resume sess_44088b8e --clear-timeouts
#  → succeeded；trace 保留了 TIMEOUT 历史 + 后续 succeeded 行
```
- 真实语料报告：`runs/sess_056e8671/report.md`
- 超时→恢复全流程：`runs/sess_44088b8e/trace.jsonl`（failed TIMEOUT attempt=1/2 → succeeded attempt=1，含 out_chars）

**修掉的真 bug（本轮新增教训）**
1. `run_session` 对已完成会话仍会再追加 `session.succeeded` → 事件流不再是「实际发生了什么」的可靠记录。修法：入口处判断「status=succeeded 且所有 steps succeeded」就原样返回；并用 `events_single_terminal_event` 断言锁死。
2. 中断类用例原本会去读不存在的 `report.md` 然后崩，而不是判决。修法：用例显式声明 `expect_no_report`，`assert_report` 先判这条再决定要不要读文件。
3. `assert_report` 在用例没声明任何 report 期望时也会要求 `report_exists`，把「只关心状态」的用例误判为红。修法：改成只有声明了 report 期望才断言 report。
4. 注入失败的 trace 行缺 `out_chars`/`out_items`/`attempt`，被新断言抓出来了。

## Week 0.6 — 2026-11-16（成本可观测 + 指数退避）
**目标**：把上轮结尾提的两项候选做完——trace 加 token/成本字段、超时改可配置退避。

- [x] `agent/cost.py`（新建）：`estimate_v1` 估算器（CJK 字 1:1 + 其余字符 ÷4 向上取整）、本地价目表 fixture、`cost_from_rates` 纯函数
- [x] trace 每行带 `estimator` / `price_id` / `price_in_per_mtok` / `price_out_per_mtok` / `tokens_in_est` / `tokens_out_est` / `cost_usd`
- [x] 费率随行落盘：日后编辑 `PRICING` 只影响新行，旧行仍可解释——这是「可复算」在时间维度上也成立的前提
- [x] `show` 增加 `trace_cost_summary`：从 trace 重算总 token 与总成本，逐行核对 `cost_usd` 与重算值的偏差，输出 `mismatches`
- [x] 指数退避：`backoff_delay_ms(attempt, base, cap) = min(base*2^(attempt-1), cap)`；每次排程写 `step.retry_scheduled` 事件（`next_attempt`/`error_code`/`delay_ms`）；`--backoff-base-ms` / `--backoff-cap-ms`
- [x] 评测集 21 → **25 条**（16 会话级 + 7 工具级 + 2 成本汇总级），新增 `retry_backoff_schedule_exponential`、`cost_fields_on_every_step`
- [x] 红证 3 → **5 处**注入，新增「改价目表使成本不再可复算」「把退避压成常数」
- [x] 断言：`trace_cost_recomputable`（按行内费率重算）、`trace_cost_nonzero_when_tokens_nonzero`（搬了字节不许报 0 成本）、`retry_delays`（事件里的退避序列必须与计划逐项相等）

**证据（命令 + 输出）**
```bash
python3 eval/run_eval.py        # → 25 / 25 passed, exit 0
python3 eval/prove_red.py       # → baseline 0；[1/5]..[5/5] 各 exit 1；"OK: gate goes red under all 5"
python3 -m agent.main run --topic "agent reliability" --input-dir corpus/notes --price-id fixture-cheap
python3 -m agent.main show sess_a1d4816f
#  → cost: {"steps":4, "tokens_in_est":369, "tokens_out_est":699, "cost_usd":0.0003165, "mismatches":[]}
python3 -m agent.main run --topic "agent" --input-dir corpus/edge --timeout-ms 1 --max-retries 3 --backoff-base-ms 400
#  → sess_b6d7b1d7 interrupted；events 里 retry_scheduled 的 delay_ms 依次 400 / 800 / 1600
```

**本轮抓出的真 bug（教训）**
1. 成本断言第一版拿「当前价目表」重算行内成本 → 注入「把价目表费率改成 0」时**门没有变红**（表被改，重算也跟着变，两边一起变所以「一致」）。修法：把费率复制到行上，断言按行内费率重算；再加「搬了字节的步骤不许 0 成本」，堵住 0 费率的平凡满足。**教训：可复算的输入必须与被校验的数在同一份记录里，否则「一致」只是当时的巧合。**
2. `assert_events` 被新加的 `expect_retry_delays` 引用 `case`，但函数签名里没有这个参数 → NameError 而非判决。修：加 `case` 形参并默认 `{}`。
3. resume 阶段沿用了首次运行的 `fail_on_step` 注入 → `resume_after_write_failure` 永远修不好（每次重跑都在同一步失败）。修：resume 用单独 kwargs，把 `fail_on_step` 置空。

**下周计划（W3–4 可靠性深化，续）**
- 超时与重试策略做成可配置（`--timeout-ms` / `--max-retries` 已有雏形，补超时中断与退避）
- Trace 增加每步 token/成本字段（为“成本可度量”铺路）
- 把 `sample_input` 换成真实语料，并扩评测集到 ≥10 条（含边界与坏输入）
- 补 3–5 家信号样本的实采链接与日期，把“待实采”改实

## Week 0.7 — 2026-11-17（把「测不准的三块」补上：职级 / 中文 / 查询退化）
**目标**：基线写完后回头查「哪些数字我其实是在拿小样本或拿错字段算的」，并把能修的修掉。

- [x] **职级分层（此前误判为「字段全 None」）**：`signals/raw/enriched_a.json` 顶层 `seniority` 确实全是 `None`，但 `enrichment.seniority` 有 **1787/4017** 有值。新增 `signals-baseline.md` §4.1 职级分层表。关键读数：`control_plane` 几乎只在 staff（16.3%）/ principal（17.4%）出现，senior 仅 7.9%、junior 3.3%；`sandbox_security` 随职级单调上行（junior 6.7% → senior 30.9% → principal 37.4%）。
- [x] **中文切片（469 条，此前只有 36/4017）**：新建 `signals/fetch_zh.py`（中文查询 + `countries=['cn']` + 正文中文字符占比 ≥30% + 标题过滤 + 按 slug 对全部 enriched 去重），产出 `signals/raw/enriched_zh.json`（cn 456 / tw 9）。新增 §4.2。
- [x] **`analyze_axes.py` 加 `--globs`**：可以只读某个 enriched 文件出表（`--globs 'enriched_zh.json' --out signals/raw/axes_report_zh.json`），中文切片与主表不混算。
- [x] **`enrichment` 字段盘点**（§1.1）：19 个键里只有 `category`/`requirements`/`posting_language`/`seniority`/`domains`/`employment_type` 覆盖率够用；`experience_years_min` 2128 条看似可用，实测是「正文里最小年数」的抽取伪影（`Sr. Manager` 的 1 年来自「1 year of **people leadership**」），**明确禁用**。
- [x] **发现并记录第 4 条口径缺陷**（§0）：搜索端点的 `q` 会把多词查询折叠成首词 —— `q=agent harness` 与 `q=agent` 都返回 100830 条，`q=zzzqqqnomatch` 返回 0。后果是 `discovery.json` 的 `matched_axis` 不代表该 JD 属于那一轴；本基线全文未引用该字段。

**证据（命令 + 输出）**
```bash
python3 signals/fetch_zh.py 400 3
#  → 智能体 raw=300 zh-kept=206；大模型 raw=300 → 431；zh total 469 (new 431)
python3 signals/analyze_axes.py --selftest     # → selftest: OK
python3 signals/analyze_axes.py --prove-red    # → prove_red: OK, selftest is falsifiable in both directions
python3 signals/analyze_axes.py --globs 'enriched_zh.json' --out signals/raw/axes_report_zh.json
#  → n=469；tool_mcp body 35.0% req14/pref2 (h/s 7.00)；harness 12.6%；eval_gate 25.6% 但 req=0
```
中文切片与主表的差异（n=469 vs n=4017）：`harness` 27.6% → **12.6%**（「Harness」在中文里多是产品名，不是 loop 机制）；`tool_mcp` hard/soft 1.81 → **7.00**（中文 JD 至少把 MCP 写在必须段）；`eval_gate` required **0**（提评测但不写成任职要求）；`cost_token` topic **0.0%**。

**本轮的三条教训**
1. **「字段是 None」要分顶层与子对象查两遍**：我先看到顶层 `seniority` 全 None 就写下「本基线不含职级分层」，隔了一轮才发现在 `enrichment.seniority` 里有 1787 条。**一个「拿不到」的结论必须标出查过哪几层。**
2. **抽取型字段要在原文里抽 3 条对账**：`experience_years_min` 覆盖率 53% 看起来很健康，实际是「正文里最小的那个年数」，把「1 year of people leadership」当成了岗位年限。按它分层会得出「经验越低越要八轴」的假趋势。
3. **查询参数被忽略时不会报错**（承接 Week 0.5 那条「参数被忽略时返回的是最新发布」）：`q` 折叠首词这件事，是靠「`agent harness` 与 `agent` 返回同一个 total」才看出来的。**任何「我按 X 检索了 N 条」的说法，都要先证明 X 真的进了查询。**

**下周计划（W3–4）**
- 中文切片推到 ≥800 条、platform/infra 标题 ≥150 条（现 469 / 80），才够做中文侧的地区/岗位化结论
- `enrichment.seniority` 覆盖率 44.5% → 需补抓或说明哪些公司不给（阈值已写进 §9）
- 按 §9 阈值等下一期复跑；本期结论保持「方向成立、不判行业级拐点」

## Week 0.7b — 2026-11-17（中文切片 469 → 1379，以及一条被证伪的阈值）
**目标**：把上一条「下周计划」里的两项待办做掉——中文切片扩量、`seniority` 覆盖率阈值。

- [x] **中文切片 469 → 1379**：`python3 signals/fetch_zh.py 900 3`，加 `AI基础设施 / 模型服务 / 智能体平台 / Agent平台 / AI平台 / AI应用 / 多智能体 / 大模型应用` 等查询。cn 1366 / tw 9，platform/infra 标题 538（39.0%）。
- [x] **撤掉一条不可能达成的阈值**：原 §9 写「`enrichment.seniority` 覆盖 ≥80%」。实测抽查 3 条无 seniority 的 `enrichment_version=0` 记录，重抓 detail 端点返回的仍是 `enrichment_version=0` + `seniority: null` —— 服务端返回**已缓存的 enrichment**，不重算。按 `source` 分组也无系统性缺口（ashby 38.8% / greenhouse 60.9% / workday 54.0% / hirist 38.3% / jobleads 45.7%）。**44.5% 是这份语料的天花板**，阈值已改为「标注分母，不做 80% 目标」。
- [x] 中文切片读数重写（§4.2）：tool_mcp hard/soft **10.75**（required 43 / pref 4）；harness 10.6%（主表 27.6%）；eval_gate 21.5% 但 hard/soft **0.67**；fresh vs stale 八轴全部「新 JD 有、老 JD 无」。

**证据（命令 + 输出）**
```bash
python3 signals/fetch_zh.py 900 3
#  → 智能体 raw=300 kept=0（已在库里）；模型服务 → 910；zh total 1379 (new 910)
python3 signals/analyze_axes.py --globs 'enriched_zh.json' --out signals/raw/axes_report_zh.json
#  → n=1379；tool_mcp 33.5% req43/pref4；harness 10.6%；context_memory 35.0%；control_plane 13.3%
```
抽样重抓证伪（用 detail 端点测 3 条）：
```
ai-powered-full-stack-engineer-...: old v=0 sen=None | new v=0 sen=None
ai-security-devops-engineer-...   : old v=0 sen=None | new v=0 sen=None
agent-data-engineer-london-...    : old v=0 sen=None | new v=0 sen=None
```

**本轮最重要的一条教训（口径级）**
中文侧「platform/infra 标题只占 17.1%」这个数，**第一版是我的查询集的属性，不是中文 JD 的属性**。首轮查询以 `智能体` / `大模型` 为主（覆盖面最广的两个词，把算法岗与应用岗全捞进来），加入 `AI基础设施 / 模型服务 / 智能体平台` 后同一指标升到 39.0%。
→ **任何「某类语料只有 X% 是 Y」的结论，必须同时公布查询集；否则那句话在描述检索词，不在描述市场。** 这条与 §0 缺陷 3（`q` 折叠首词）是同一个病的两个面：**语料的边界是我选的，不是世界给的。**

**顺带得到的一个反向核对**
中文 `context_memory` 35.0% 明显低于主表 42.6%。主表的 42.6% 里，印度样本（791 条，19.7%）的 context_memory 是 69.2%。中文切片不含印度，读数更接近「无模板化倾向」的基线。**这提示主表的 42.6% 可能被印度 JD 的模板化写法抬高了**——已写进 §4.2，但不下结论（缺一个「印度剔除后」的受控口径，下期补）。

**下周计划**
- 补「剔除印度」的受控口径，验证主表 context_memory 42.6% 是否被抬高
- 中文切片按「平台岗 / 非平台岗」做一次内部分层（现已有 538 条分母）
- 按 §9 阈值等下一期复跑

## Week 0.7c — 2026-11-17（标题家族交叉：把「平台岗 = 目标读者」这个默认假设测掉）
**目标**：`cohorts` 里 `platform_named` mean_axes 只有 1.41 一直被当成「平台岗要求少」解释。本轮把 AI 名与平台名两个独立正则交叉，看是哪一个字带来了那八个轴。

- [x] `analyze_axes.py` 新增 `TITLE_AI` / `TITLE_PLATFORM` / `title_family()` / `MIN_FAM_N = 40`，`analyze()` 返回 `"title_families"`，CLI 打印 `title families` 表
- [x] 新增 `title_family_selftest()`（7 条中英混合标题做断言），接进 `selftest()`
- [x] `prove_red()` 扩到 **4 处注入**：③ 把标题正则换回英文-only → `family selftest` 必须变红
- [x] `signals-baseline.md` 新增 §4.3（英文 + 中文两张家族表 + 剔印复核 + 两条口径教训）

**核心结论（英文 n=4017）**
| 家族 | n | context_mem | tool_mcp | harness | mean |
|---|---|---|---|---|---|
| `ai_only` | 1722 | **65.5%** | 49.9% | 41.8% | **2.56** |
| `ai_and_platform` | 454 | 44.9% | 42.1% | 38.8% | 2.37 |
| `platform_only` | 1363 | **18.8%** | 16.1% | 11.9% | **1.20** |
| `neither` | 478 | 26.2% | 21.8% | 10.5% | 1.44 |

**平台标题的岗（SRE / Infrastructure / Architect）八轴均值 1.20，是四个家族里最低的**——比 `neither` 还低。八轴不是「基础设施岗的升级版」，是「AI 岗的基础设施侧」。中文侧方向相反：`ai_and_platform` 2.57 > `ai_only` 1.68（「大模型应用算法」几乎不谈 harness/tool_mcp，「智能体平台」才谈）。

**证据（命令 + 输出）**
```bash
python3 signals/analyze_axes.py --selftest     # → family selftest: OK / selftest: OK  exit 0
python3 signals/analyze_axes.py --prove-red    # → 4 处各红；"falsifiable under all 4 injected violations" exit 0
python3 signals/analyze_axes.py                # → title families 表（英文 n=4017）
python3 signals/analyze_axes.py --globs 'enriched_zh.json' --out signals/raw/axes_report_zh.json
#  → ai_and_platform 178/2.57、ai_only 778/1.68、platform_only 311/1.36、neither 112/1.50
```

**本轮抓出的两个真 bug**
1. **标题分类器英文-only**：第一次跑中文切片，**64.2%（886/1379）**被判成 `neither`——和轴词表最初纯英文时「中文侧整块漏测」是同一个错误换了一层。修：正则加 `智能体|大模型|平台|基础设施|中台|架构师|系统架构|执行引擎`；`neither` 从 64.2% 降到 8.1%。
2. **`\bai\b` 进 `TITLE_AI` 会毁掉精度**：加上后 `ai_and_platform` 从 454 条膨胀到 1419 条（35.3%），均值从 2.37 掉到 **1.70** —— "AI Data Engineer" / "GenAI-Driven Data Platforms" 被算成 AI agent 岗。修：删掉裸 `\bai\b`，只留 `agent|agentic|llm|ai engineer|genai|applied ai|ml engineer|智能体|大模型`。**召回涨 3 倍、精度崩 4 成，等于把「AI 岗」偷换成「提到 AI 的岗」。**

**对求职的含义（这条比数字重要）**
按 §4.3，简历里把自己定位成「Agent Infra 平台工程师」会落进 `platform_only` 那一格（均值 1.20、context_memory 18.8%）；而真实的要求集中在 `ai_only`（均值 2.56、context_memory 65.5%）。**正确的定位是「AI 应用/智能体工程师，且带基础设施能力」，不是「平台工程师，且会点 AI」。**

**下周计划**
- §9 阈值等下一期复跑（`tool_mcp` 受控 ≥60% 且 `runtime` hard_soft ≥1.2 = 拐点确认）
- 中文侧 `ai_and_platform` 只有 178 条，若要出结论需再补量
- 把 §4.3 的家族结论回填进 README 的「这个项目测什么」
