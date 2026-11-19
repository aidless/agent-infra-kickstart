# 标准化评测数据集 spec（对齐 JD「构建场景化标准化评测数据集 / 评测集管理」）

> 这是「评测执行框架的数据集」：每条数据是一个**输入 + 期望标签 + 复现命令**，
> 用来管理评测用例、判分依据与回放。不是模型质量评测结果。
> 边界：本仓库无 LLM、无视觉算法（CV/SLAM）数据，不编造那类数据集。

## 一、schema（eval-dataset/v1）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | 用例名，与 `cases.json` 的 `name` 一一对应 |
| `input` | obj | 输入：`corpus`（语料目录）/ `tool`（工具调用）/ `fail_on_step`（注入点）等 |
| `expected_label` | obj | 期望标签：以 `expect_` 开头的断言（`expect_status` / `expect_report_contains` / `expect_files_analyzed` …），即**判分依据** |
| `axis` | str | 能力轴：`plan`（会话级）/ `tool`（工具级）/ `cost`（成本汇总级） |
| `verdict_on_contract` | bool | 当前契约产物（`last_contract.json`）里该用例的通过状态，可复算 |
| `source` | str | 来源文件（`eval/cases/cases.json`） |
| `reproduce` | str | 复现命令（`python3 eval/run_eval.py <id>`） |

## 二、与 cases.json 的关系

- `cases.json` 是**运行时用例定义**（输入 + 断言），`dataset_sample.json` 是它的**数据集视图**
  （加了 axis / verdict / source / reproduce，方便管理、检索、回放）。
- 两者一一对应；改 cases.json 必须同步重跑 `gen_dataset_sample.py` 更新数据集视图。

## 三、如何加一条数据

1. 在 `eval/cases/cases.json` 加用例（含 `expect_*` 判分依据）。
2. 在 `eval/run_eval.py` 加对应断言（`run_plan_case` / `run_tool_case` / `run_cost_case`）。
3. 跑 `python3 eval/run_eval.py` 全绿。
4. 跑 `python3 eval/gen_dataset_sample.py` 重生成 `dataset_sample.json`。
5. 更新 `eval/COVERAGE.md`（用例名 / 语料 / 测什么 / 关键断言，数字与实际一致）。

## 四、判分纪律

- 期望标签必须是**可判据的**（能比对出 pass/fail），不许写「应该通过」这类空话。
- 每条数据必须能由 `reproduce` 命令复现；复现不出来 = 数据集损坏。
- 判分依据从 cases.json 提取，不许手写一份与运行时脱节的「期望」。

## 五、当前规模（可复算）

- 用例总数：28（plan 16 / tool 10 / cost 2），见 `eval/last_contract.json`。
- 数据集视图样例：`eval/dataset_sample.json`（6 条代表，每 axis 2 条）。
- 生成命令：`python3 eval/gen_dataset_sample.py`。
