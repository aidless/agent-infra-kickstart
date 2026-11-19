# 变更记录

## [0.1.0] - 2026-11-19

首次公开发布。

### 包含

- **agent 运行时**：`run_session` 单一终态出口，步骤化执行 + 可中断可恢复（`state.json`）+ 成本可复算（`trace.jsonl` 每行带 token/rate）。
- **5 个工具**：`list_files` / `extract_keywords` / `write_text` / `summarize_text` / `read_file_window`（窗口化读取，服务端硬上限 200 行 / 20000 字符，调用方不能绕过）。
- **pre-stop verifier + 空 diff guard**（`agent/finish_guard.py`）：产物非空 → `.py` 可编译 → 调用方 `verify_cmd` 通过，三项任一失败即 `blocked_by_guard`，只落 append-only event 不污染成本 trace。
- **MCP 暴露**：`mcp_server.py` 5 个工具定义，`eval/mcp_selftest.py` 11 例（含「新工具必须在最终输出里」的内容断言，不只断言总数）。
- **评测**：`eval/run_eval.py` 28 例（含 3 条工具级窗口用例）+ `eval/prove_red.py` 5 处注入必红 + `eval/mcp_selftest.py --prove-red` 3 处必红。
- **测试**：`tests/test_finish_guard.py` 19 例。

### 证据锚点

- 空 diff guard / pre-stop verifier 的设计依据：arXiv:2611.22299 Table IV（modular harness 未验证退出 0% vs prompt-only 30%）。
- 窗口化读取的依据：arXiv:2611.21688（上下文增长带来的时延与噪声）。

### 已知边界

- 运行时本身不调用 LLM（工具层零依赖）；模型通道由调用方注入。
