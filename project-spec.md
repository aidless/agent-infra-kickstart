# 最小 Agent 系统规格（Project Spec）

> 启动日期：2026-11-16  
> 目标：8–12 周内做出一个“端到端可运行、可中断可恢复、可观测、可评测”的小型 Agent 系统，作为 Agent/AI Infra 基础能力的证明。

## 1. 场景（长任务，可中断）
**选定场景（本地可复现，无外部依赖）**：  
“给定一个本地目录与主题，Agent 多步完成：列出文件 → 读取并提取关键信息（词频/行数/命中）→ 生成结构化报告 → 产出摘要归档。”

**要求**：
- 4 个步骤、4 个工具调用（`list_files` / `extract_keywords` / `write_text` / `summarize_text`）。
- 每步落盘、可中断；恢复时跳过已成功步骤，重放不产生重复副作用（同内容写入记为 no-op）。

## 2. 状态模型（必须落盘）
| 对象 | 字段（建议） | 说明 |
|---|---|---|
| Session | `session_id`, `goal`, `created_at`, `status` | 一次任务会话 |
| Turn/Step | `step_id`, `input`, `action`, `output`, `error`, `started_at`, `ended_at` | 每一步执行记录 |
| Event | `event_id`, `type`, `payload`, `ts` | 追加式事件流，便于回放与审计 |
| Artifact | `artifact_id`, `path|uri`, `version`, `checksum` | 产出物与版本 |

**持久化**：本地文件/SQLite 均可；必须支持按 `session_id` 读取并继续未完成步骤。  
**幂等**：同一步重放不产生重复副作用，或通过去重键/检查点避免重复写入。

## 3. 工具与治理（逐步加入）
- 统一工具接口：`name / version / input_schema / output / error`。
- 权限与审计：工具调用参数与结果摘要写入事件/日志；敏感凭据不落盘明文。
- **已实现**：`mcp_server.py` 实现 MCP 规范 2025-06-18 的 stdio 传输与 JSON-RPC 2.0 生命周期（initialize/版本协商/initialized/tools/list/tools/call/ping），把 4 个工具注册为带 inputSchema 的 MCP tools；`write_text` 保持 PATH_ESCAPE 沙盒；`eval/mcp_selftest.py` 11 项检查 + 3 处注入反证。

## 4. 可观测与评测
- **观测**：结构化日志 + Trace（step 耗时、工具调用、错误码），能定位一次失败到具体步骤。
- **评测集**：覆盖典型/边界/失败用例（初始 ≥10 条），记录输入、期望行为/输出要点。
- **门禁**：任意改动前后跑评测并对比（成功率、时延、成本/调用次数），退化需解释或回滚。

## 5. 分阶段里程碑与验收
| 阶段 | 目标 | 验收证据 |
|---|---|---|
| W1–2 最小闭环 | Agent Loop + 工具调用 + 状态落盘 | 可运行 demo；中断后可从状态继续或安全重试 |
| W3–4 可靠性 | 幂等/重试/超时 + Trace | 可复现并定位一次失败；重放无重复副作用 |
| W5–6 上下文与治理 | 上下文组装/简单记忆 + 工具版本与审计 | 工具可替换；异常/越权被拦与留痕；成本取舍说明 |
| W7–8 评测与门禁 | 评测集 + 回归对比 + Gate | 改动有前后数据；Bad Case 可回流 |
| 持续 | ReAct/Workflow/Planner-Executor 对比 | 架构取舍 1 页 + 代码/运行记录 |

## 6. 当前决策（已填充基线，可按实际调整）
- 场景与领域：本地文档/代码目录的主题化信息提取与报告生成（长任务、可中断、离线可复现；后续可替换为真实检索/抓取工具）
- 工具清单（≥2）：`list_files`（枚举输入）、`extract_keywords`（统计与命中提取）、`write_text`（生成报告，幂等）、`summarize_text`（归档摘要）
- 持久化方案：本地文件（`runs/<session_id>/state.json` 状态快照 + `events.jsonl` 追加式事件流 + `trace.jsonl` 步骤 Trace + 产出文件），按 `session_id` 恢复
- 语言与运行环境：Python 3.12（标准库，无额外依赖），在 `agent-infra-kickstart/` 下 `python3 -m agent.main ...` 运行
- 首个验收日期：2026-11-23（W1 收口：中断恢复、Trace、评测集雏形与 ≥10 家信号基线全部可复现）

### 6.1 可靠性机制（2026-11-16 已落地，W3–4 提前完成）
| 机制 | 契约 | 落点 |
|---|---|---|
| 步骤级超时 | `Step.timeout_ms`（None=不限）；工具内部协作式查钟，每 200 次迭代一次；超时抛 `ToolTimeout` → `error_code=TIMEOUT` | `agent/state.py`、`agent/tools.py`（`set_deadline`/`_tick`）、`agent/runner.py` |
| 失败分级 | 可重试码（`TIMEOUT`/`EXCEPTION`/`LIST_ERROR`/`EXTRACT_ERROR`/`WRITE_ERROR`/`SUMMARIZE_ERROR`）耗尽重试后 → `interrupted`，剩余步骤保持 `pending`；输入类错误（`BAD_INPUT`/`NOT_FOUND`/`PATH_ESCAPE`）→ `failed` | `agent/tools.py` `RETRYABLE_ERROR_CODES`、`agent/runner.py` |
| 完成态幂等 | `status=succeeded` 且全部步骤 succeeded 时 `run_session` 直接返回，不追加第二条终态事件 | `agent/runner.py` |
| Trace 体积代理 | 每行带 `out_chars`/`out_items`/`attempt`；这是输出体积，不是 token，也不是钱 | `agent/tools.py` `measure_output`、`agent/runner.py` |
| 成本可复算 | 每行记 `estimator`/`price_id`/`price_in_per_mtok`/`price_out_per_mtok`/`tokens_in_est`/`tokens_out_est`/`cost_usd`，费率随行落盘，价目表日后改动不影响旧行解释；`show` 汇总时逐行重算，`mismatches` 必须为空 | `agent/cost.py`、`agent/main.py` `trace_cost_summary` |
| 指数退避 | `backoff_delay_ms(attempt, base, cap) = min(base*2^(attempt-1), cap)`；`base=0` 关掉等待但仍在事件流里记录计划；每次排程都写 `step.retry_scheduled` 事件 | `agent/runner.py` |
| 评测门禁 | 25 条用例（16 会话级 + 7 工具级 + 2 成本汇总级）+ 5 处注入反证 | `eval/run_eval.py`、`eval/cases/cases.json`、`eval/prove_red.py`、`eval/COVERAGE.md` |
| 语料 | `sample_input/`（合成 3 文件）+ `corpus/notes/`（4 篇真实笔记 41 KB）+ `corpus/edge|mixed|truly_empty|one_file|binary/`（边界） | `corpus/`、`corpus/make_edge.py`（生成物重建） |
