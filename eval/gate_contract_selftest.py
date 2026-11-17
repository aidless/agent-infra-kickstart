from __future__ import annotations

"""Selftest for the eval gate contract.

Discipline (verification-gate): a gate that cannot go red is decoration.
Every fault class below feeds a *known-bad* input and asserts the verdict
moves off PASS with the right exit code and a first-line `problems=N`.

Also ships --prove-red: replace the judge with an always-PASS stub and assert
that this selftest itself fails. If the stub still passes, the selftest is an
ornament and must not be trusted.
"""

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from eval.gate_contract import (  # noqa: E402
    EXIT_FAIL,
    EXIT_NOT_RUN,
    EXIT_PASS,
    EXIT_USAGE,
    build_contract,
    not_run_on_write_failure,
    write_contract,
)

_JUDGE = Callable[..., Dict[str, Any]]
_OK_SHA = {"cases": "a" * 12, "runner": "b" * 12, "contract": "c" * 12}
_BASE_THRESH = {"min_total": 2, "max_failed": 0, "require_modes": ["plan", "tool"]}


def _row(name: str, mode: str, passed: bool) -> Dict[str, Any]:
    return {
        "case": name,
        "mode": mode,
        "passed": passed,
        "checks": [{"name": "assert_1", "pass": passed, "got": passed, "want": True}],
        "metrics": {"duration_ms": 7, "steps": 1, "cost_usd": 0.001},
    }


def _good_results() -> List[Dict[str, Any]]:
    return [_row("a", "plan", True), _row("b", "tool", True)]


def _assert_case(
    name: str,
    judge: _JUDGE,
    results: Any,
    thresh: Any,
    sha: Any,
    want_verdict: str,
    want_exit: int,
) -> Tuple[bool, str]:
    try:
        c = judge(results, thresholds=thresh, content_sha12=sha)
    except Exception as exc:  # a raised exception on a known-bad input is not PASS either
        return True, f"{name}: raised {type(exc).__name__} (not PASS)"
    got_v, got_e = c.get("verdict"), c.get("exit_code")
    summary = str(c.get("summary", ""))
    ok = got_v == want_verdict and got_e == want_exit
    if want_verdict != "PASS":
        # problems=N must be on the first line and N must be non-zero; a red
        # verdict with problems=0 is a lying summary.
        import re as _re
        m = _re.search(r"problems=(\d+)", summary)
        ok = ok and m is not None and int(m.group(1)) > 0
    return ok, f"{name}: verdict={got_v} exit={got_e} summary={summary!r}"


def run_selftest(judge: _JUDGE = build_contract) -> Tuple[int, List[str]]:
    checks: List[Tuple[bool, str]] = []

    # 0) clean input must be PASS (if the baseline is red, every red below is meaningless)
    checks.append(_assert_case("baseline_pass", judge, _good_results(), _BASE_THRESH, _OK_SHA, "PASS", EXIT_PASS))

    # 1) value drift: flip one passed True->False
    drift = _good_results()
    drift[1]["passed"] = False
    drift[1]["checks"][0]["pass"] = False
    checks.append(_assert_case("value_drift", judge, drift, _BASE_THRESH, _OK_SHA, "FAIL", EXIT_FAIL))

    # 2) threshold out of range
    checks.append(_assert_case(
        "threshold_too_high", judge, _good_results(),
        {**_BASE_THRESH, "min_total": 99}, _OK_SHA, "USAGE", EXIT_USAGE,
    ))

    # 3) hash drift: content cannot be identified
    checks.append(_assert_case(
        "hash_drift", judge, _good_results(), _BASE_THRESH,
        {**_OK_SHA, "runner": "NOT_A_HASH"}, "NOT_RUN", EXIT_NOT_RUN,
    ))

    # 4) nothing executed: did-not-run must not be silently green
    checks.append(_assert_case("empty_results", judge, [], _BASE_THRESH, _OK_SHA, "NOT_RUN", EXIT_NOT_RUN))

    # 5) structural hole: a row with no assertions
    hollow = _good_results()
    hollow[0]["checks"] = []
    checks.append(_assert_case("no_assertions", judge, hollow, _BASE_THRESH, _OK_SHA, "NOT_RUN", EXIT_NOT_RUN))

    # 6) required mode missing
    checks.append(_assert_case(
        "missing_mode", judge, [_row("a", "plan", True), _row("b", "plan", True)],
        _BASE_THRESH, _OK_SHA, "FAIL", EXIT_FAIL,
    ))

    # 7) write failure: a contract that was not persisted is NOT_RUN, not PASS
    c = judge(_good_results(), thresholds=_BASE_THRESH, content_sha12=_OK_SHA)
    err = write_contract(c, Path("/dev/null/impossible_contract.json"))
    promoted = not_run_on_write_failure(c, err or "injected failure")
    ok = (
        promoted["verdict"] == "NOT_RUN"
        and promoted["exit_code"] == EXIT_NOT_RUN
        and "不等于通过" in str(promoted["summary"])
        and "problems=" in str(promoted["summary"])
    )
    checks.append((ok, f"write_failure: verdict={promoted['verdict']} summary={promoted['summary']!r}"))

    lines = [f"[{'ok' if ok else 'FAIL'}] {detail}" for ok, detail in checks]
    return sum(1 for ok, _ in checks if ok), lines


def prove_red() -> int:
    """Replace the judge with always-PASS; the selftest must collapse."""
    def always_pass(results: Any, *, thresholds: Any, content_sha12: Any) -> Dict[str, Any]:
        total = len(results) if isinstance(results, list) else 0
        return {
            "verdict": "PASS", "exit_code": EXIT_PASS, "problems": [],
            "summary": f"eval-gate: verdict=PASS problems=0 total={total} passed={total} failed=0",
            "total": total, "passed": total, "failed": 0, "cases": [],
        }

    good, _ = run_selftest(build_contract)
    stub, lines = run_selftest(always_pass)
    print(f"baseline selftest: {good}/8 ok")
    for line in lines:
        print("  " + line)
    if good != 8:
        print("FAIL: baseline selftest is not 8/8")
        return 1
    if stub == 8:
        print("FAIL: selftest stays green under always-PASS stub (decoration)")
        return 1
    print(f"OK: selftest goes red under injected always-PASS judge ({stub}/8 ok)")
    return 0


def main() -> int:
    if "--prove-red" in sys.argv:
        return prove_red()
    good, lines = run_selftest(build_contract)
    for line in lines:
        print(line)
    print(f"gate_contract_selftest: {good}/8 ok")
    return 0 if good == 8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
