# 可观测性：trace.jsonl 与 OTel 的语义等价

> 声明：这是**语义等价说明**，不是 OTel SDK 实现。本仓库不引入第三方遥测依赖；
> 下表说明 `runs/<sid>/trace.jsonl` 的字段如何对应 OTel 的 trace/span 语义，
> 需要时可按此映射手工导出 OTel JSON/Protobuf。

## 字段映射

| trace.jsonl 字段 | OTel 语义 | 说明 |
|---|---|---|
| 会话（session_id，一个 trace.jsonl 对应一个会话） | trace_id | 同一会话内所有步骤共享一个 trace |
| `step.name` + `attempt` | span.name（如 `step:extract_info#1`） | 每次重试是独立 span，`attempt` 标明第几次 |
| `status`（succeeded / failed / interrupted） | span status code | succeeded → OK；failed / interrupted → ERROR |
| `error_code`（TIMEOUT / NOT_FOUND / PATH_ESCAPE / BAD_INPUT …） | status.message + attributes | 失败原因写进状态，不丢 |
| `duration_ms` | span duration | 每步耗时 |
| 参数摘要（`args` 摘要） | span attributes | 输入参数记录 |
| `out_chars` / `out_items` | attributes.output.size.bytes / attributes.output.items | 输出体积代理（非 token） |
| `estimator` / `price_id` / `tokens_in_est` / `tokens_out_est` / `cost_usd` | 业务 attributes（`cost.usd`、`cost.tokens.in/out`、`cost.price_id`） | 成本字段是业务属性，非 OTel 标准，放 attributes |
| 会话 → 步骤 | 根 span → 子 span（parent_span_id = 会话 span） | 步骤是会话下的子 span |

## 可观测能力（可复算、可回放）

1. **全量落盘**：每步一条 trace，事件流 `events.jsonl` 与状态 `state.json` 同步，三者互验。
2. **可回放复现**：重放 trace 行即可还原每步的输入、输出、错误码与重试序号；
   `run_eval.py` 的 `trace_matches_state` 断言锁死「trace 不许替 state 撒谎」。
3. **错误历史不丢**：`trace_error_code_history` 断言保证历史错误码不被最后一次成功覆盖。
4. **成本可复算**：`cost_usd == tokens × 行内费率 ÷ 1e6` 逐行校验，`mismatches` 必须为空。

## 边界

- 不输出 OTel 标准 JSON/Protobuf；语义等价指字段对应关系成立。
- `out_chars`/`out_items` 是体积代理，不是 token，也不是钱。
- 成本用本地 fixture 价目表，不是厂商报价（测「可复算、可比较」，不是账单）。
