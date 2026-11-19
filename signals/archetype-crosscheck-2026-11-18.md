# 交叉验证尝试：用 freehire 官方 archetype 独立核验核心结论（2026-11-18）

## 结论先给

**这次"独立验证"没成功，但失败本身是有价值的发现：freehire 的 `ai_archetype` 与我们手搓的 8 轴词表同源（共线），不是独立数据源，不能用来验证核心结论。**

- 铁证：`agent_builder`、`rag_app_builder` 两个原型的 `context_memory` 命中率都是 **100.0%**（n=300 each）。官方分类器若独立于我们的正则，不可能出现确定性命中。
- 第二证据：6 个原型的 AI-word 命中率全部 95–100%，所谓"infra 对照组"根本不存在——全是 AI 岗。预注册的 P2 判据（传统 infra 侧 runtime/control_plane 更高）前提被证伪。
- 因此门输出 `state=NOT_RUN`（exit 3），措辞含「not run is not a pass」。**不是**为了让门变绿而调阈值，而是加同源守卫拒绝出判决——方向更严。

## 为什么值得做

`signals-baseline.md` 的核心结论——"八轴是 AI 岗的基础设施侧，不是基础设施岗的 AI 升级"——此前靠我们自己写的标题家族正则（§4.3）。若正则有偏，结论就是正则的伪影。这次想用平台自己的分类器（独立来源）交叉验证。

## 实测数据（同源，仅描述，不可当独立验证）

| 原型 | n | context_memory | tool_mcp | AI-word | junior 占比 |
|---|---|---|---|---|---|
| agent_builder | 300 | 100.0% | — | 100% | — |
| fullstack_ai_engineer | 300 | 55.0% | — | 98% | — |
| rag_app_builder | 300 | 100.0% | — | 100% | — |
| cloud_ml_platform_engineer | 300 | 45.0% | — | 100% | — |
| devops_infra_engineer | 300 | 52.0% | — | 95% | — |
| ml_trainer_researcher | 300 | 2.0% | — | 97% | — |

- ai-builder 侧（agent_builder + fullstack_ai_engineer）vs 平台-ML 侧（cloud_ml + devops）：`context_memory` 77.5%/48.5%、`tool_mcp` 44.0%/22.5%，gap **0.2525** ≥ 预注册 0.10 → 方向上**看似**强支撑结论。
- junior 占比 3.53% > 1.71% → 方向上一致。
- **但**因为同源，这两条都只能当"同一把尺量的描述"，不能当独立验证。P2 的 runtime/control_plane gap = −0.0075（方向相反且前提已废）。

## 落盘产物

- `signals/verify_archetype.py`：预注册判据 P1/P2/P3 + 同源守卫（`max_cm ≥ 0.95` → NOT_RUN）+ 三处反证。
- `signals/raw/archetype_samples.json`：6 类 × 300 条样本（1800 条，带 description_html）。
- `signals/archetype_facets.json`：6 类 facets（seniority 等）。

## 门禁状态（全绿）

```
python3 signals/verify_archetype.py            → problems=0 state=NOT_RUN ... circular=True max_cm=1.0，exit 3
python3 signals/verify_archetype.py --prove-red → 3/3 反证全过，exit 0
  [1/3] 关掉同源守卫 → 同一份循环数据吐出假绿 SUPPORTED（证明守卫是唯一挡假阳的东西）
  [2/3] 分类器塌缩（全塞一个原型）→ 拒判 NOT_RUN
  [3/3] 平凡仪器（每句命中所有轴）→ 标记为坏仪器，不给 SUPPORTED
```

## 新查清的事实（可复算）

- **薪资拿不到（继续"待核"，不编造）**：公共 search API 的 `enrichment` 不含薪资数值；facets 里只有 `salary_currency`（USD 247460 / RUB 332316 / … 共 1092373 条带货币标记）与 `salary_period`（month 687568 / year 220158 / hour 143908 / day 4746），**没有 min/max 分位数**。所以薪资区间本机仍无法核验，与既有"待核"口径一致。
- **官方 archetype 全库分布**：ml_trainer_researcher 5923 / rag_app_builder 3032 / agent_builder 1758 / fullstack_ai_engineer 1371 / cloud_ml_platform_engineer 896 / devops_infra_engineer 301。这类岗位总量小（合计 13k），且高度重叠于我们已经分析过的语料。
- **agent_builder 的 seniority**：junior 31 / middle 33 / senior 475 / lead 171 / staff 48 / principal 69 / c_level 28 / intern 36——高级岗占绝对多数，初级入口窄。

## 下一步（未做，等用户定）

1. 换真正独立的数据源验证核心结论（如 LinkedIn/Wellfound 自有分类，而非聚合站的衍生标签）。
2. 把这次"同源验证陷阱"作为方法论教训补进 `signals-baseline.md` 的口径缺陷清单（将是第 6 条）。
3. 顺着 junior 入口窄这个发现，专门挖 agent/eval 方向的初级岗清单。
