# 评测集覆盖表（28 条）

> 运行：`python3 eval/run_eval.py`（全绿 exit 0）／`python3 eval/run_eval.py <case_name>`（单条）
> 红证：`python3 eval/prove_red.py`（5 处注入，每处必须 exit≠0）
> 契约层：`eval/last_contract.json` 是给 CI 消费的机器可读结果；首行 `eval-gate: verdict=... problems=N`，exit 0 PASS / 1 FAIL / 2 用法错 / 3 闸没执行（不等于通过）。8 类故障见红：`python3 eval/gate_contract_selftest.py`；自检自身的反证：`--prove-red`（always-PASS 桩下从 8/8 掉到 2/8）。每条 case 的 `metrics` 带 duration_ms 与从该会话 trace 逐行重算的 tokens/cost；正控用例故意篡改的那 1 处 mismatch 在契约里保留。
> 语料全部本地落盘，无网络依赖，无时间随机性；语料根见 `eval/run_eval.py` 的 `CORPUS` 字典。
> MCP 协议门：`python3 eval/mcp_selftest.py`（11 项：握手/版本协商/未握手拦截/tools-list 4 工具/读调用/幂等写/沙盒逃逸/未知工具/协议错误码/batch/真实 stdio 子进程）；反证 `--prove-red` 注入 3 处违规（isError 失效 / 工具表清空 / 握手门跳过）每处必红。
> MCP 端到端门：`python3 eval/mcp_e2e.py`（12 项：真 client 经 stdio 跑 initialize→tools/list→list_files→extract_keywords→write_text→summarize_text→read_file_window→幂等写→PATH_ESCAPE→未知工具）；反证 `--prove-red` 把 step3 期望写错必红。

## 一、会话级（16 条，走完整默认 4 步计划）

| # | 用例 | 语料 | 它到底在测什么 | 关键断言 |
|---|---|---|---|---|
| 1 | `happy_path` | `sample_input`（3 文件） | 干净路径的端到端产出 | status=succeeded；report 三节齐全；`Files analyzed: 3`；≥5 关键词 |
| 2 | `resume_after_write_failure` | `sample_input` | 第 3 步注入失败后 resume 补齐，前两步不重跑 | status=succeeded；report 内容完整；trace 覆盖所有尝试过的步骤 |
| 3 | `fail_fast_no_resume` | `sample_input` | 不 resume 时必须停在中断态，且**没有** report | status=interrupted；error_code=SIMULATED；只在 `extract_info` 出错；`report_absent` |
| 4 | `missing_input_dir` | `/tmp/definitely_not_here_xyz` | 坏输入目录的错误分类 | status=failed；error_code=NOT_FOUND；`report_absent` |
| 5 | `real_corpus_notes` | `corpus/notes`（4 篇真实笔记，41 KB） | 真实长文本（含中文、代码块）不被当边界样本打挂 | 4 文件；≥5 关键词；`trace_out_chars_min>=1000`（输出确实带内容，不是空壳通过） |
| 6 | `real_corpus_nested_only` | `corpus/edge/nested`（1 文件） | 只给子目录时相对路径解析仍正确 | 1 文件 |
| 7 | `edge_mixed_empty_and_binary` | `corpus/mixed`（空/单行/无词） | 空文件与无关键词文件不阻断整批 | status=succeeded；3 文件；report 含 `one_line.txt` |
| 8 | `edge_truly_empty_dir` | `corpus/truly_empty` | 空目录 → 空 paths → 输入校验拦下 | status=failed；error_code=BAD_INPUT；`report_absent` |
| 9 | `edge_binary_decode_tolerated` | `corpus/binary`（非 UTF-8） | 解码容错（errors=replace）而非崩 | status=succeeded；1 文件 |
| 10 | `step_timeout_interrupts_then_resumes` | `corpus/edge`（689 KB / 5 文件） | 步骤级超时真的触发，且清理预算后可续跑 | trace 里留下 `error_code=TIMEOUT` 历史；最终 succeeded；report 有 `## Top keywords` |
| 11 | `retry_budget_then_interrupt` | `corpus/edge` | 重试耗尽后进入**可恢复中断**（不是 failed） | status=interrupted；error_code=TIMEOUT；`min_attempts>=2`；`report_absent` |
| 12 | `rerun_idempotent_report` | `sample_input` | 完成后再跑一遍不重复写 | status=succeeded；3 文件；`session.succeeded` 事件 ≤1 |
| 13 | `resume_after_complete_is_noop` | `sample_input` | 完成态 resume 是真空转（不追加终态事件） | 同上：`events_single_terminal_event` 必须成立 |
| 14 | `edge_single_empty_file` | `corpus/empty_only`（1 个仅空白文件） | 「目录非空但内容为空」不被误判成 `BAD_INPUT` | status=succeeded；1 文件；report 含 `only_empty.txt` 与关键词节 |
| 15 | `retry_backoff_schedule_exponential` | `corpus/edge` | 退避序列是 base×2^(n-1) 且被 cap 截断，且真的写进事件流 | `expect_retry_delays=[200,400,400]`（base=200, cap=400, retries=3）；`min_attempts>=4`；interrupted |
| 16 | `cost_fields_on_every_step` | `corpus/notes` | 每步 token/价格/成本可复算，且用非默认价目表也自洽 | `trace_cost_recomputable`（按行内记下的费率重算）；`trace_cost_nonzero_when_tokens_nonzero`；`price_id=fixture-cheap` |

## 二、工具级（10 条，直接调 4 个工具，不经会话）

| # | 用例 | 测什么 | 关键断言 |
|---|---|---|---|
| 14 | `tool_list_files_nested_glob` | 递归 glob + limit；相对目录在 input_dir 下解析 | `count=5`（`corpus/edge` 全部文件，含嵌套与 `.bin`/`.json`） |
| 15 | `tool_path_escape_blocked` | 写穿跑目录必须被拒 | `ok=false`；`PATH_ESCAPE` |
| 16 | `tool_write_idempotent_second_call` | 同内容二次写 | 第二次 `written=false, idempotent=true`；文件存在 |
| 17 | `tool_extract_keywords_bad_input` | 空 paths 是输入错误不是崩溃 | `ok=false`；`BAD_INPUT` |
| 18 | `tool_extract_keywords_missing_file` | 不存在的文件路径 | `ok=false`；`NOT_FOUND` |
| 19 | `tool_summarize_real_doc` | 真实文档摘要字段 | 输出 `path` 以 `doc2.md` 结尾 |
| 20 | `tool_unknown_tool_rejected` | 注册表必须封闭 | 未注册工具被拒（`UNKNOWN_TOOL`），不许静默通过 |
| 21 | `tool_read_file_window_page` | 按行分页读取（`start_line`/`max_lines`） | `expect_output_value`：`start_line=1`、`returned_lines=3` |
| 22 | `tool_read_file_window_oversized_params_rejected` | 服务端硬上限：`max_lines` 超限必须拒绝 | `expect_tool_ok=false`；`error_code=BAD_INPUT` |
| 23 | `tool_read_file_window_missing_file` | 不存在文件 | `expect_tool_ok=false`；`error_code=NOT_FOUND` |

## 三、成本汇总级（2 条，先跑完整计划再核对 trace 汇总）

| # | 用例 | 测什么 | 关键断言 |
|---|---|---|---|
| 24 | `cost_summary_clean_rows` | 干净 trace 的总 token/总成本可重算 | `cost_mismatch_count=0`；总成本 >0；总 token ≥500 |
| 25 | `cost_summary_detects_tampered_row` | **检测器的正控**：手工把某行 `cost_usd` 改大，必须被报出 | `cost_mismatch_count=1` |

> 成本汇总级的 2 条是配对的「能红」证明：只断言「mismatches 为空」的检测器，永远为空也照样通过。

## 四、断言分层（所有会话级用例共同生效）

| 层 | 断言 | 为什么单列 |
|---|---|---|
| 状态 | `status` / `prefix_integrity` / `all_steps_done` 或 `pending_preserved_for_resume` | 首次失败之前的步骤必须全 succeeded；中断后剩余步骤必须留 pending，否则续跑不成立 |
| Trace | `trace_exists` / `trace_jsonl_parses` / `trace_covers_attempted` / `trace_duration_ms_int` / `trace_output_size_fields` / `trace_matches_state` / `trace_error_code_history` | 「失败后可观测」的核心：历史错误码不能被最后一次成功覆盖掉；trace 不许替 state 撒谎 |
| 成本 | `trace_cost_recomputable` / `trace_cost_nonzero_when_tokens_nonzero` | 成本必须能从行内字段重算（token × 行内费率 ÷ 1e6），且搬了字节的步骤不许报 0 成本——否则「可复算」会被 0 费率平凡满足 |
| 事件 | `events_exist` / `events_jsonl_parses` / `events_first_is_session_created` / `events_single_terminal_event` / `retry_delays` | 事件流是 append-only 记录，终态事件重复 = 记录失真；退避序列必须与算出来的计划逐项相等 |
| 产出 | `report_exists` / `report_contains:*` / `report_excludes:*` / `files_analyzed` / `min_keywords` / `report_absent` | 中断用例必须能断言「此刻确实没有产出」，否则「没报错」会被误当成果 |

## 五、有意不测的部分（防过度宣称）

- **不测模型行为**：这里没有 LLM，只有确定性工具与状态机。所谓「评测门禁」测的是运行时契约，不是模型质量。
- **不测并发**：单进程串行执行，没有锁竞争与并行步。
- **不测真实成本**：`tokens_in_est`/`tokens_out_est` 来自 `estimate_v1`（CJK 字 1:1 + 其余字符 ÷4 向上取整）这条粗略启发式，不是 tokenizer 输出；`cost_usd` 用的是本地价目表 fixture，不是厂商报价。这里测的是「成本字段可复算、可比较、不撒谎」，不是账单。
- **不测真实时钟**：超时预算用极小值（1 ms）触发，目的是验证控制流可中断、可恢复；不验证调度精度。

## 六、新增用例的规矩

1. 先写断言再写实现——断言写成用例 JSON，跑一次看它红，再改代码让它绿。
2. 每条新断言都要问「它能不能红」：能红才进 `prove_red.py` 的注入清单，或者至少手动注入一次确认。
3. 语料必须落盘到 `corpus/` 并在 `CORPUS` 注册，禁止在测试里临时生成随机内容。
4. 中断/失败类用例必须显式声明 `expect_no_report`，否则断言会在缺失文件上崩，而不是给出判决。
5. 断言「某个数可复算」时，重算所需的输入必须与那个数在同一行/同一份产物里。只把输入放在一张会变的全局表里，「可复算」就只是当时成立——编辑表的那一刻旧数就失去解释。
