# Agent Infra Kickstart（2026-11-16 启动）

目标：并行推进两条线  
1. **打基础**：做一个端到端、可中断可恢复、可观测、可评测的最小 Agent 系统。  
2. **判拐点**：用固定样本做招聘/产品/生态信号跟踪，识别 Agent Infra 何时从试点进入规模化生产。

## 快速开始（在 `agent-infra-kickstart/` 下）
```bash
# 1) 跑一次完整流程（枚举本地输入 → 提取关键词 → 生成报告 → 归档摘要）
python3 -m agent.main run --topic "Agent Infra" --input-dir sample_input

#    真实语料（本工作区 notes/ 里复制来的 4 篇笔记，41 KB）
python3 -m agent.main run --topic "agent reliability" --input-dir corpus/notes

#    超时演示：1 ms 预算 + 重试 1 次 → interrupted，清预算后 resume 补齐
python3 -m agent.main run --topic "agent" --input-dir corpus/edge --timeout-ms 1 --max-retries 1
python3 -m agent.main resume <session_id> --clear-timeouts

# 2) 演示中断 → 恢复（第 3 步注入失败）
python3 -m agent.main run --topic "Agent Infra" --input-dir sample_input --fail-on-step write_report
python3 -m agent.main resume <session_id>

# 3) 看状态（含从 trace 重算的 token/成本汇总，mismatches 必须为空）
python3 -m agent.main show <session_id>

#    退避 + 非默认价目表
python3 -m agent.main run --topic "agent" --input-dir corpus/edge --timeout-ms 1 --max-retries 3 --backoff-base-ms 400 --price-id fixture-cheap

# 4) 评测门禁（28 个用例：16 条会话级 + 10 条工具级 + 2 条成本汇总级，全绿退出 0）
python3 eval/run_eval.py

#    只跑单条（调试用）
python3 eval/run_eval.py step_timeout_interrupts_then_resumes

#    契约产物：eval/last_contract.json（首行 eval-gate: verdict=... problems=N；exit 0/1/2/3）
#    exit 0 PASS / 1 FAIL / 2 用法错 / 3 闸没执行（不等于通过）

# 5) 反证：证明门禁能红（5 处注入违规 → 每处都必须非零退出）
python3 eval/prove_red.py

#    契约层自检：8 类故障见红 + always-PASS 桩下自检自身变红
python3 eval/gate_contract_selftest.py
python3 eval/gate_contract_selftest.py --prove-red

# 6) JD 信号基线：自检 + 双向反证 + 出表
python3 signals/analyze_axes.py --selftest
python3 signals/analyze_axes.py --prove-red
python3 signals/analyze_axes.py
python3 signals/analyze_axes.py --globs 'enriched_zh.json' --out signals/raw/axes_report_zh.json  # 中文切片

# 7) 真 MCP server（stdio + JSON-RPC 2.0，把 5 个工具注册为 MCP tools）
python3 eval/mcp_selftest.py            # 11 项协议/沙盒/真实 stdio 子进程检查，全绿 exit 0
python3 eval/mcp_selftest.py --prove-red  # 3 处注入（isError/tool list/握手门）每处必须红
# 手动握手示例（stdin 一行一个 JSON-RPC 消息，stdout 只出协议）：
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"demo","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 mcp_server.py --run-dir runs/demo --input-dir sample_input

# 8) 榜单管理 + 回归检测（对齐 JD「榜单管理/回归检测」）
python3 eval/board.py --rank          # 榜单：按 通过/mode/name 排序，含成本/耗时列
python3 eval/board.py --save-baseline # 存基线（绑定 content_sha12）
python3 eval/board.py --regression    # 回归对比，有回归 exit 1
python3 eval/board.py --selftest      # 自检（构造数据验排序与回归检出）
python3 eval/board.py --prove-red     # 桩下自检必红
```

## 产物位置（每次运行一个目录）
- `runs/<session_id>/state.json` — 状态快照（Session/Step，含 status/output/error_code/duration_ms）
- `runs/<session_id>/events.jsonl` — 追加式事件流（created/step.started/step.x/session.x）
- `runs/<session_id>/trace.jsonl` — 每步 Trace（工具、耗时、错误码、参数摘要、`attempt` 重试序号、`out_chars`/`out_items` 输出体积，以及可复算的成本字段：`estimator`/`price_id`/`price_in_per_mtok`/`price_out_per_mtok`/`tokens_in_est`/`tokens_out_est`/`cost_usd`）
- `runs/<session_id>/report.md` — 产出物（幂等：同内容重写记为 `written=false`）

## 已实现能力（W1 最小闭环）
| 能力 | 实现位置 | 验证方式 |
|---|---|---|
| 状态模型落盘 + 恢复跳过已成功步骤 | `agent/state.py`、`agent/runner.py` | 中断→resume 后 `draft` 不重跑、后续步骤补跑 |
| 幂等写入 | `agent/tools.py` `write_text` | 同内容二次写入 `written=false, idempotent=true` |
| 路径逃逸防护 | `agent/tools.py` `_resolve_inside` | `../escape.md` → `PATH_ESCAPE` |
| 运行轨迹 Trace（耗时/错误码/参数摘要，支持回放复现） | `agent/state.py` `append_trace`、`agent/runner.py` | `trace.jsonl` 每步一条，可回放复现 |
| 步骤级超时控制（协作式 deadline） | `agent/tools.py` `set_deadline`/`_tick`、`agent/runner.py` | `timeout_ms` 注入后 `error_code=TIMEOUT`，失败重试 1 次仍失败 → `interrupted` 且后续步骤保持 pending |
| 失败重试与分级：可重试 → interrupted，不可重试 → failed | `agent/tools.py` `RETRYABLE_ERROR_CODES`、`agent/runner.py` | `BAD_INPUT`/`NOT_FOUND`/`PATH_ESCAPE` 直接 failed；`TIMEOUT` 等留 pending 可续跑 |
| 完成后再 resume 是 no-op | `agent/runner.py` | 第二次 resume 不再追加 `session.succeeded` 事件 |
| 失败重试指数退避（`backoff_delay_ms`） | `agent/runner.py` | `base=200, cap=400, retries=3` → 事件流里恰好 `[200, 400, 400]` |
| 成本可复算 | `agent/cost.py`、`agent/main.py` `trace_cost_summary` | 行内记下费率，`cost_usd == tokens × 行内费率 ÷ 1e6` 逐行校验；`show` 的 `mismatches` 必须为空 |
| 评测门禁 + 红证 | `eval/run_eval.py`、`eval/prove_red.py` | 28/28 绿；5 处注入违规 → 各自 exit 1 |
| 空 diff guard（终态前） | `agent/finish_guard.py` `empty_diff_guard`、`agent/runner.py` | 无产物且无 written 声明 → `EMPTY_DIFF`，记 `session.blocked_by_guard`；账本类文件不计入 |
| pre-stop verifier（终态前） | `agent/finish_guard.py` `prestop_verify` | 产物非空 → .py 可编译 → `AIK_VERIFY_CMD` rc=0，三项全过才记 `succeeded` |
| 窗口化文件视图 | `agent/tools.py` `read_file_window` | 按行分页 + 服务端硬上限（200 行 / 20000 字符），超限 `truncated=true` 且给 `next_start` |
| 真 MCP server（stdio） | `mcp_server.py`、`eval/mcp_selftest.py` | 5 工具注册为 MCP tools，握手/版本协商/isError/沙盒全绿；3 处注入各红 |
| 榜单管理 + 回归检测 | `eval/board.py` | `--rank` 榜单（按 通过/mode/name 排序，含成本/耗时列）；`--save-baseline` 存基线；`--regression` 对比，有回归 exit 1（注入 happy_path 失败 → 检出 1 条回归 exit 1）；`--selftest`/`--prove-red` 双门 |

## 本周立即执行（Week 0）
- [x] 确认项目场景与最小范围（见 [project-spec.md](project-spec.md)）
- [x] 完成首次 JD/信号基线（见 [signals-baseline.md](signals-baseline.md)：4017 条真实 JD 正文级测量，替换旧的手抄骨架）
- [x] 建立每周节奏与证据留存（见 [weekly-log.md](weekly-log.md)）

## 目录
- `project-spec.md`：最小 Agent 系统的场景、状态模型、工具与验收标准
- `signals-baseline.md`：拐点信号基线——8 轴正文级读数、共现、月内趋势、判定档位与下期阈值
- `signals/`：采集与测量管线，`fetch_freehire.py`（72 查询 → 11638 条）→ `classify.py`（三档分类）→ `enrich_tier_a.py`（4017 条带正文）→ `analyze_axes.py`（8 轴测量 + 职级分层 + 标题家族交叉，带 `--selftest` 与 `--prove-red` 四处注入）；`fetch_zh.py` 单独抓中文切片（**1379 条**，`--globs 'enriched_zh.json'` 分开出表，不与主表混算）
- `weekly-log.md`：每周产出与复盘记录（代码/实验/看板更新留证）
- `agent/`：最小 Agent 实现（state / tools / runner / main）
- `eval/`：评测用例、门禁、红证脚本；[COVERAGE.md](eval/COVERAGE.md) 是 28 条用例的逐条覆盖表（16 会话级 + 10 工具级 + 2 成本汇总级，含「有意不测的部分」）
- `sample_input/`：合成的小语料（3 文件，快速回归用）
- `corpus/`：真实语料与边界样本——`notes/`（从本工作区 `notes/` 复制的 4 篇真实笔记）、`edge/`（空文件/非 UTF-8/单行/20k 行大文件/嵌套目录）、`mixed/`、`truly_empty/`、`one_file/`、`binary/`

## 已知边界
- 无 LLM：全确定性工具 + 状态机，评测测的是运行时契约，不是模型质量。
- 单进程串行：没有并发步、没有锁竞争。
- `out_chars`/`out_items` 是输出体积代理，不是 token 也不是钱。
- `tokens_in_est`/`tokens_out_est` 来自 `estimate_v1` 启发式（CJK 字 1:1 + 其余字符 ÷4 向上取整），不是 tokenizer 输出；`cost_usd` 用本地价目表 fixture，不是厂商报价。测的是「可复算、可比较」，不是账单。
- 超时用 1 ms 极小预算触发，验的是「可中断可恢复」的控制流，不是调度精度。
- JD 语料来自单一聚合站（freehire.me，约 50 个 ATS），含美国 26% / 印度 19.7% / 中国 1.4%。**顶层 `seniority` 全为 `None`，`enrichment.seniority` 只有 44.5% 有值且是上游天花板（重抓不重算）**，职级结论只能落在 1787 条上。中文切片单独抓了 1379 条（`fetch_zh.py`），但**构成由我的查询集决定**（首轮 30 查询只有 17.1% 平台岗，扩查询后 39.0%），不能当中国市场的无偏代表值。
- **标题家族交叉（§4.3）是这份基线最重要的边界**：`platform_only` 标题（SRE / Infrastructure / Architect）八轴均值 1.20、`context_memory` 18.8%，是四家族里最低；真实要求集中在 `ai_only`（均值 2.56、`context_memory` 65.5%）。**按「平台工程师」定位自己会落进要求最少的那一格。**

## 原则
- 以**可运行、可复现、可度量**为准，不以“看过/了解”为完成。
- 每次改动都应能回答：成功率/成本/时延/可控性发生了什么变化，证据在哪。
- 门禁必须能红（`eval/prove_red.py`），否则是装饰。
