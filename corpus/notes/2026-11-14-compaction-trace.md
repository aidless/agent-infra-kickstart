# 压缩轨迹 — session-70746f9f-5dad-4cc0-bc80-d46735b72fd6

源：`/home/liuzewen/.dsh/sessions/--home-liuzewen-F-deepseek--/session-70746f9f-5dad-4cc0-bc80-d46735b72fd6/session.v4.jsonl.zstd`

| 字段 | 值 | 说明 |
|---|---|---|
| enabled | True | 日志里有压缩事件 |
| triggerCount | 1 | 压缩次数 |
| pruneCount | 4 | 被折叠的单条消息数 |
| tokensFreedTotal | 12914 | 各 prune 的 shadowedTokenCount 之和 |
| failures | 0 | 压缩失败事件 |
| checkCount | null | 平台只记触发、不记每次检查 |
| contextWindow / reserveTokens / keepRecentTokens | null | 日志不记录 |

## 逐次压缩

| # | turn | 折叠消息数 | 释放 tokens | summary 字符 |
|---|---|---|---|---|
| 1 | 18 | 4 | 12914 | 38039 |
