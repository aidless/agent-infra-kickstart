from __future__ import annotations

"""Machine-readable gate contract for the eval harness.

This is the *verdict layer*, not a second eval runner: eval/run_eval.py still
executes every case and owns all assertions. This module only turns those
results into a consumable artifact with an explicit verdict and exit code,
so a CI job never has to guess whether a green line means "ran and passed"
or "never ran".

Exit codes (verification-gate discipline):
    0 PASS     - executed, every case passed, every threshold met
    1 FAIL     - executed, but an assertion or a declared threshold failed
    2 USAGE    - caller gave an impossible threshold/config
    3 NOT_RUN  - no trustworthy result existed; "did not run" != "passed"

Every contract carries content_sha12 so a consumer can tell which bytes were
actually judged. A contract whose inputs cannot be identified is NOT_RUN.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "eval-gate-contract/v1"
EXIT_PASS, EXIT_FAIL, EXIT_USAGE, EXIT_NOT_RUN = 0, 1, 2, 3
_EXIT = {"PASS": EXIT_PASS, "FAIL": EXIT_FAIL, "USAGE": EXIT_USAGE, "NOT_RUN": EXIT_NOT_RUN}
_ALLOWED_MODES = {"plan", "tool", "cost"}


def sha12(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def is_sha12(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 12 and all(c in "0123456789abcdef" for c in value)


def _summary(verdict: str, problems: List[str], total: int, passed: int, failed: int) -> str:
    # First line must expose problems=N; no truth is allowed to hide in body.
    # NOT_RUN carries the required wording: 闸没执行不等于通过.
    suffix = "  # 闸没执行不等于通过" if verdict == "NOT_RUN" else ""
    return (
        f"eval-gate: verdict={verdict} problems={len(problems)} "
        f"total={total} passed={passed} failed={failed}{suffix}"
    )


def build_contract(
    results: List[Dict[str, Any]],
    *,
    thresholds: Dict[str, Any],
    content_sha12: Dict[str, str],
) -> Dict[str, Any]:
    """Judge already-executed case results. Pure: no IO, no clock, no imports of the runner.

    results items are the dicts returned by run_plan_case / run_tool_case /
    run_cost_case, optionally enriched with a `metrics` field by the caller.
    """
    problems: List[str] = []
    total = len(results)
    passed = sum(1 for r in results if r.get("passed") is True)
    failed = total - passed

    # A gate that executed zero cases has no evidence. NOT_RUN wins over every
    # other verdict: "not executed does not mean passed".
    if total == 0:
        problems.append("no_cases_executed: empty result set is NOT a pass (did not run != passed)")
        verdict = "NOT_RUN"
        return _finalize(verdict, problems, total, passed, failed, results, thresholds, content_sha12)

    # Usage: impossible thresholds are the caller's error, not the suite's fault.
    min_total = thresholds.get("min_total")
    max_failed = thresholds.get("max_failed", 0)
    require_modes = thresholds.get("require_modes", [])
    if not isinstance(min_total, int) or isinstance(min_total, bool) or min_total < 0:
        problems.append("usage: min_total must be a non-negative int")
    elif min_total > total:
        problems.append(f"usage: min_total={min_total} > executed cases={total}")
    if not isinstance(max_failed, int) or isinstance(max_failed, bool) or max_failed < 0:
        problems.append("usage: max_failed must be a non-negative int")
    if not isinstance(require_modes, (list, tuple)) or any(m not in _ALLOWED_MODES for m in require_modes):
        problems.append(f"usage: require_modes must only contain {sorted(_ALLOWED_MODES)}")
    if problems:
        return _finalize("USAGE", problems, total, passed, failed, results, thresholds, content_sha12)

    # Structural integrity: an unreadable row cannot be silently counted green.
    for i, r in enumerate(results):
        name = r.get("case", f"row[{i}]")
        if not isinstance(r.get("passed"), bool):
            problems.append(f"{name}: passed is not bool")
        checks = r.get("checks")
        if not isinstance(checks, list) or not checks:
            problems.append(f"{name}: no assertions recorded (did not run != passed)")
        elif any(not isinstance(c, dict) or "pass" not in c for c in checks):
            problems.append(f"{name}: malformed assertion row")
        if r.get("mode") not in _ALLOWED_MODES:
            problems.append(f"{name}: unknown mode {r.get('mode')!r}")
    for key, value in content_sha12.items():
        if not is_sha12(value):
            problems.append(f"content_sha12[{key}] is not sha256[:12] ({value!r})")

    if problems:
        return _finalize("NOT_RUN", problems, total, passed, failed, results, thresholds, content_sha12)

    # Thresholds: declared, enumerable, checked one by one.
    if passed < min_total:
        problems.append(f"min_total: passed={passed} < {min_total}")
    if failed > max_failed:
        problems.append(f"max_failed: failed={failed} > {max_failed}")
    seen_modes = {r.get("mode") for r in results}
    for mode in require_modes:
        if mode not in seen_modes:
            problems.append(f"require_modes: no case with mode={mode}")

    verdict = "PASS" if not problems else "FAIL"
    return _finalize(verdict, problems, total, passed, failed, results, thresholds, content_sha12)


def _finalize(
    verdict: str,
    problems: List[str],
    total: int,
    passed: int,
    failed: int,
    results: List[Dict[str, Any]],
    thresholds: Dict[str, Any],
    content_sha12: Dict[str, str],
) -> Dict[str, Any]:
    by_mode: Dict[str, Dict[str, int]] = {}
    for r in results:
        m = r.get("mode", "unknown")
        slot = by_mode.setdefault(m, {"total": 0, "passed": 0, "failed": 0})
        slot["total"] += 1
        slot["passed" if r.get("passed") is True else "failed"] += 1
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "exit_code": _EXIT[verdict],
        "problems": problems,
        "summary": _summary(verdict, problems, total, passed, failed),
        "total": total,
        "passed": passed,
        "failed": failed,
        "by_mode": by_mode,
        "thresholds": thresholds,
        "content_sha12": content_sha12,
        "cases": [
            {
                "name": r.get("case"),
                "mode": r.get("mode"),
                "passed": r.get("passed"),
                "checks": r.get("checks", []),
                "metrics": r.get("metrics"),
            }
            for r in results
        ],
    }


def write_contract(contract: Dict[str, Any], path: Path) -> Optional[str]:
    """Write the contract JSON. Returns None on success, error text on failure.

    A failure to persist the artifact is itself NOT_RUN: CI reading a stale or
    missing contract must never be told that the gate passed.
    """
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return None
    except (OSError, TypeError, ValueError) as exc:
        return f"{type(exc).__name__}: {exc}"


def not_run_on_write_failure(contract: Dict[str, Any], err: str) -> Dict[str, Any]:
    """Promote a write failure to NOT_RUN and say so in the first-line summary."""
    out = dict(contract)
    problems = list(out.get("problems", [])) + [
        f"contract_write_failed: {err}; a contract that was not written does not mean passed "
        "(闸没执行不等于通过)"
    ]
    out["problems"] = problems
    out["verdict"] = "NOT_RUN"
    out["exit_code"] = EXIT_NOT_RUN
    out["summary"] = _summary("NOT_RUN", problems, out.get("total", 0), out.get("passed", 0), out.get("failed", 0))
    return out
