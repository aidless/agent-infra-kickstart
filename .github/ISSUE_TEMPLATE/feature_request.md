---
name: Feature request
about: 提议一个新能力、新评测用例或新门禁
title: "[feature]: 简短描述"
labels: enhancement
assignees: ''
---

## 动机
<!-- 为什么要加这个能力/用例/门禁？对应哪个能力维度或 JD 关键词？ -->

## 建议方案
<!-- 具体怎么加：新用例放在 cases.json 的哪个 mode？新断言是什么？新门禁的 --prove-red 怎么注入？ -->

## 验收标准
- [ ] `python3 eval/run_eval.py` 全绿
- [ ] `python3 eval/prove_red.py` 每处仍红（或新门禁的反证成立）
- [ ] `eval/COVERAGE.md` 已同步，数字与实际一致
- [ ] 不引入新第三方依赖（除非明确说明理由）

## 补充
- 相关文件 / 用例名：
