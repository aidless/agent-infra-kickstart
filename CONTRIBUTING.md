# 贡献指南（CONTRIBUTING）

本仓库是「最小 Agent 运行时 + 评测门禁」的教学/求职用项目。欢迎提 issue 与 PR。

## 一、复现前置

改动前先跑通现有门禁（全部应绿）：

```bash
python3 eval/run_eval.py              # 28 用例，全绿 exit 0
python3 eval/prove_red.py             # 5 处注入，每处必须 exit 1
python3 eval/mcp_selftest.py          # 11 项，全绿 exit 0
python3 eval/mcp_selftest.py --prove-red
python3 eval/gate_contract_selftest.py
python3 eval/gate_contract_selftest.py --prove-red
python3 eval/board.py --selftest
python3 eval/board.py --prove-red
```

## 二、加一条评测用例的流程

1. 在 `eval/cases/cases.json` 加用例（`mode`：`plan` / `tool` / `cost`）。
2. 在 `eval/run_eval.py` 的 `run_plan_case` / `run_tool_case` / `run_cost_case` 里加断言，
   并确认断言是**可判据的**（不能只写「应该通过」）。
3. **门必须能红**：能断言「会失败」的用例，必须配一条注入违规让门变红的反证。
   新门加 `--prove-red`，否则是装饰。
4. 更新 `eval/COVERAGE.md`：把用例名、语料、测什么、关键断言填上，**数字与实际用例数一致**。
5. 跑 `python3 eval/run_eval.py` 全绿、`python3 eval/prove_red.py` 每处红，再提交。

## 三、改门 / 改断言的纪律

- **先改断言，再改实现**：把判据写死，再动代码，避免「改代码顺带改判据」。
- 每个新闸配 `--selftest`（构造数据验证）+ `--prove-red`（注入违规必须红）。
- 回归检测、成本复算等判据，必须从落盘产物重算，不许在断言里复制实现逻辑后互相印证。

## 四、数字纪律

- 任何百分比 / 样本量 / 用例数，必须能从落盘产物重算；重算不一致 = 阻塞。
- 不写没做过的能力（没做过的标「未做 / 未装」，不写成「有」）。
- 成本、token 是启发式估计（见 `README.md` 已知边界），不当作真实账单。

## 五、PR 流程

1. 分支名描述任务（如 `feat/board-ranking`）。
2. **只 `git add` 自己改的文件**，不 `add -A`，不夹带他人改动。
3. 提交前 `git diff --cached --stat` 看文件数与行数；逐行读 staged diff，出现自己没写过的 `+` 行要注明来源或拆分。
4. 合并前确认所有门禁绿（`eval/run_eval.py`、`prove_red.py`、`mcp_selftest.py`、`board.py`）。

## 六、目录约定

- `agent/`：运行时实现（state / tools / runner / main / cost / finish_guard）。
- `eval/`：用例、门禁、红证、榜单、契约。
- `mcp_server.py`：真 MCP server（stdio + JSON-RPC 2.0）。
- `signals/`：JD 信号采集与测量管线（求职/研究用，数据较大，私有脚本已 gitignore）。
- `corpus/`：真实语料与边界样本。

## 七、提 issue

用 `.github/ISSUE_TEMPLATE/` 里的模板（bug 报告 / 功能请求），描述清楚复现命令与预期 vs 实际。
