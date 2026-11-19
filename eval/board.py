#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最小榜单系统：榜单管理 + 回归检测（对齐 JD「榜单管理/回归检测/回归检测」关键词）。

读 eval/last_contract.json（run_eval.py 的契约产物）：
  --rank       输出榜单（按 通过降序 / mode / name），带成本与耗时列
  --baseline   把当前榜单存为基线 eval/baseline.json（绑定 content_sha12）
  --regression 对比基线 vs 当前：有「基线通过、现在失败」的用例 → 列回归 + exit 1；无回归 exit 0
  --inject-case NAME   证明用：把指定用例强制标 failed（不碰真实 last_contract，内存中改）
  --selftest   用构造数据验证 rank 排序与 regression 检出
  --prove-red  把 regression 检出换成恒空桩 → selftest 必须红（门能红）

判据纪律：
  - 回归判定只看「基线 passed=True 且当前 passed=False」；反向（修好）单列 fixed，不算回归。
  - 基线缺失 → NOT_RUN（exit 3），不许把「没基线」当成「无回归」。
  - 成本列来自行内 metrics（cost_usd），不重算厂商价。
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_CONTRACT = ROOT / "eval" / "last_contract.json"
DEFAULT_BASELINE = ROOT / "eval" / "baseline.json"

EXIT_PASS, EXIT_FAIL, EXIT_USAGE, EXIT_NOT_RUN = 0, 1, 2, 3


def load_contract(path: Path) -> dict:
    d = json.load(open(path, encoding="utf-8"))
    if "cases" not in d or "verdict" not in d:
        raise ValueError(f"not a contract: {path}")
    return d


def rank_rows(contract: dict) -> list:
    rows = []
    for c in contract["cases"]:
        m = c.get("metrics") or {}
        rows.append({
            "name": c["name"], "mode": c.get("mode", ""),
            "passed": bool(c.get("passed")),
            "cost_usd": m.get("cost_usd"), "duration_ms": m.get("duration_ms"),
            "steps": m.get("steps"), "tokens_in_est": m.get("tokens_in_est"),
            "tokens_out_est": m.get("tokens_out_est"),
            "cost_mismatches": m.get("cost_mismatches"),
        })
    rows.sort(key=lambda r: (not r["passed"], r["mode"], r["name"]))
    return rows


def render_board(rows: list) -> str:
    head = "| # | 用例 | mode | 通过 | 成本USD | 耗时ms | 步数 | tokens_in | tokens_out | 成本不一致 |"
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    lines = [head, sep]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | {r['name']} | {r['mode']} | {'PASS' if r['passed'] else 'FAIL'} | "
            f"{r['cost_usd']} | {r['duration_ms']} | {r['steps']} | "
            f"{r['tokens_in_est']} | {r['tokens_out_est']} | {r['cost_mismatches']} |")
    return "\n".join(lines)


def find_regressions(baseline: dict, current: dict):
    b = {c["name"]: bool(c.get("passed")) for c in baseline["cases"]}
    reg, fixed = [], []
    for c in current["cases"]:
        name, now = c["name"], bool(c.get("passed"))
        if name in b and b[name] and not now:
            reg.append(name)
        if name in b and not b[name] and now:
            fixed.append(name)
    return reg, fixed


def cmd_rank(contract_path: Path) -> int:
    d = load_contract(contract_path)
    rows = rank_rows(d)
    print(d["summary"])
    print(render_board(rows))
    return EXIT_PASS


def cmd_baseline(contract_path: Path, baseline_path: Path) -> int:
    d = load_contract(contract_path)
    payload = {
        "baseline_sha12": d.get("content_sha12"),
        "summary": d["summary"],
        "cases": [{"name": c["name"], "passed": bool(c.get("passed"))} for c in d["cases"]],
    }
    baseline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"baseline saved: {baseline_path} ({len(payload['cases'])} cases, "
          f"sha12={payload['baseline_sha12']})")
    return EXIT_PASS


def cmd_regression(baseline_path: Path, current_path: Path, inject: str | None) -> int:
    if not baseline_path.exists():
        print(f"NOT_RUN: baseline missing {baseline_path} — run --baseline first; "
              "not run is not a pass")
        return EXIT_NOT_RUN
    base = json.load(open(baseline_path, encoding="utf-8"))
    cur = load_contract(current_path)
    if inject:
        for c in cur["cases"]:
            if c["name"] == inject:
                c["passed"] = False
    reg, fixed = find_regressions(base, cur)
    if reg:
        print(f"REGRESSION detected ({len(reg)}): " + ", ".join(reg))
        if fixed:
            print(f"fixed ({len(fixed)}): " + ", ".join(fixed))
        return EXIT_FAIL
    print(f"no regression: baseline[{base['summary']}] vs current[{cur['summary']}]")
    if fixed:
        print(f"fixed ({len(fixed)}): " + ", ".join(fixed))
    return EXIT_PASS


def _selftest() -> int:
    problems = []
    base = {"cases": [{"name": "a", "passed": True}, {"name": "b", "passed": True},
                      {"name": "c", "passed": True}]}
    cur = {"cases": [{"name": "a", "passed": True}, {"name": "b", "passed": False},
                     {"name": "c", "passed": True}]}
    reg, fixed = find_regressions(base, cur)
    if reg != ["b"]:
        problems.append(f"regression detect: want ['b'] got {reg}")
    if fixed:
        problems.append(f"fixed should be empty got {fixed}")
    # rank 排序：失败的排最后
    rows = rank_rows({"cases": [
        {"name": "z", "mode": "plan", "passed": True, "metrics": {"cost_usd": 1}},
        {"name": "a", "mode": "plan", "passed": False, "metrics": {"cost_usd": 0}},
        {"name": "m", "mode": "tool", "passed": True, "metrics": {"cost_usd": 2}},
    ]})
    order = [r["name"] for r in rows]
    # 排序键 (not passed, mode, name)：通过在前；同状态按 mode 字母序 plan<tool；失败最后
    if order != ["z", "m", "a"]:
        problems.append(f"rank order: want ['z','m','a'] (pass 先按 mode 字母序, fail 最后) got {order}")
    # 基线缺失 → NOT_RUN
    rc = cmd_regression(Path("/tmp/__no_such_baseline__.json"), DEFAULT_CONTRACT, None)
    if rc != EXIT_NOT_RUN:
        problems.append(f"missing baseline should be NOT_RUN got {rc}")
    n = len(problems)
    print(f"board selftest: problems={n} " + ("PASS" if n == 0 else "FAIL"))
    for p in problems:
        print("  -", p)
    return EXIT_PASS if n == 0 else EXIT_FAIL


def _prove_red() -> int:
    """把回归检出换成恒空桩 → selftest 的回归检出断言必须红。"""
    global find_regressions
    orig = find_regressions
    find_regressions = lambda base, cur: ([], [])
    try:
        problems = []
        base = {"cases": [{"name": "a", "passed": True}]}
        cur = {"cases": [{"name": "a", "passed": False}]}
        reg, _ = find_regressions(base, cur)
        if not reg:
            problems.append("stub returned empty regression for a real fail (expected)")
        # 桩下 selftest 的回归检出断言会红
        rc = _selftest()
        print(f"prove-red: stub active, selftest rc={rc} (want !=0)")
        ok = rc != EXIT_PASS and problems
        print("prove-red: " + ("OK: board goes red under stubbed regression detector"
                              if ok else "FAIL: board did not go red"))
        return EXIT_PASS if ok else EXIT_FAIL
    finally:
        find_regressions = orig


def main() -> int:
    ap = argparse.ArgumentParser(description="最小榜单系统：榜单管理 + 回归检测")
    ap.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    ap.add_argument("--rank", action="store_true")
    ap.add_argument("--save-baseline", action="store_true")
    ap.add_argument("--regression", action="store_true")
    ap.add_argument("--inject-case", default=None,
                    help="证明用：把指定用例强制标 failed（内存中改，不写盘）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--prove-red", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if args.prove_red:
        return _prove_red()
    if args.rank:
        return cmd_rank(Path(args.contract))
    if args.save_baseline:
        return cmd_baseline(Path(args.contract), Path(args.baseline))
    if args.regression:
        return cmd_regression(Path(args.baseline), Path(args.contract), args.inject_case)
    print("usage: board.py --rank | --save-baseline | --regression [--inject-case NAME] "
          "| --selftest | --prove-red")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
