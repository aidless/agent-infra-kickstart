#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从真实 cases.json + last_contract.json 实例化「标准化评测数据集」样例。

对齐 JD 关键词「构建场景化标准化评测数据集 / 评测集管理 / 判分依据」。
诚实边界：这是「评测执行框架的数据集」（输入/期望/轴/来源/复现命令），
不是模型质量评测结果；视觉算法（CV/SLAM）数据集本仓库没有，不编造。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "eval" / "cases" / "cases.json"
CONTRACT = ROOT / "eval" / "last_contract.json"
OUT = ROOT / "eval" / "dataset_sample.json"


def main() -> int:
    cases = json.load(open(CASES, encoding="utf-8"))
    cases = cases["cases"] if isinstance(cases, dict) and "cases" in cases else cases
    contract = json.load(open(CONTRACT, encoding="utf-8"))
    passed = {c["name"]: bool(c.get("passed")) for c in contract["cases"]}

    by_mode = {}
    for c in cases:
        by_mode.setdefault(c.get("mode", "plan"), []).append(c)

    items = []
    for mode, lst in by_mode.items():
        for c in lst[:2]:  # 每 mode 取 2 条代表
            name = c["name"]
            inp = {}
            if "corpus" in c:
                inp["corpus"] = c["corpus"]
            if "tool" in c:
                inp["tool"] = c["tool"]
            if "fail_on_step" in c:
                inp["fail_on_step"] = c["fail_on_step"]
            exp = {k: v for k, v in c.items()
                   if k.startswith("expect_") and k not in ("expect_no_report",)}
            items.append({
                "id": name,
                "input": inp,
                "expected_label": exp,
                "axis": mode,
                "verdict_on_contract": passed.get(name),
                "source": "eval/cases/cases.json",
                "reproduce": f"python3 eval/run_eval.py {name}",
            })

    ds = {
        "schema": "eval-dataset/v1",
        "name": "kickstart-standard-eval-dataset",
        "description": "标准化评测数据集样例：从 28 条用例实例化，每条含 input/expected_label/axis/来源/复现命令",
        "axes": sorted(by_mode.keys()),
        "item_count": len(items),
        "items": items,
    }
    OUT.write_text(json.dumps(ds, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"dataset_sample.json: {len(items)} items, axes={ds['axes']}")
    for it in items:
        print(f"  {it['axis']:5s} {it['id']:45s} verdict={it['verdict_on_contract']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
