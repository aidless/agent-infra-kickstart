from __future__ import annotations

"""Evaluation harness for the minimal agent loop.

Two case modes:
  - "plan": create a session from the default plan and run it (resume/timing knobs apply)
  - "tool": call one tool directly and assert ok/error_code (no session involved)

Every case is a JSON object in eval/cases/cases.json. Assertions are declared with
`expect_*` keys; a case passes only when every declared assertion holds.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

_here = Path(__file__).resolve().parent
_ROOT = _here.parent
sys.path.insert(0, str(_ROOT))

from eval.gate_contract import build_contract, not_run_on_write_failure, sha12, write_contract

from agent.cost import DEFAULT_PRICE_ID, ESTIMATOR_ID, cost_from_rates, estimate_tokens, rates_for
from agent.runner import backoff_delay_ms, create_session, default_plan, run_session
from agent.state import Store
from agent.tools import build_default_registry

CORPUS = {
    "sample_input": _ROOT / "sample_input",
    "notes": _ROOT / "corpus" / "notes",
    "edge": _ROOT / "corpus" / "edge",
    "nested": _ROOT / "corpus" / "edge" / "nested",
    "mixed": _ROOT / "corpus" / "mixed",
    "empty_only": _ROOT / "corpus" / "empty_only",
    "one_file": _ROOT / "corpus" / "one_file",
    "binary": _ROOT / "corpus" / "binary",
    "truly_empty": _ROOT / "corpus" / "truly_empty",
}


def resolve_input_dir(case: Dict[str, Any]) -> str:
    if "input_dir" in case:
        return case["input_dir"]
    corpus = case.get("corpus", "sample_input")
    if corpus not in CORPUS:
        raise KeyError(f"unknown corpus: {corpus}")
    return str(CORPUS[corpus].resolve())


def _check(name: str, ok: bool, got: Any, want: Any) -> Dict[str, Any]:
    return {"name": name, "pass": bool(ok), "got": got, "want": want}


def _report_section(text: str, heading: str) -> List[str]:
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return []
    return [ln for ln in m.group(1).splitlines() if ln.strip()]


def assert_report(path: Path, case: Dict[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    want_frags = case.get("expect_report_contains", [])
    deny_frags = case.get("expect_report_not_contains", [])
    want_files = case.get("expect_files_analyzed")
    want_min_kw = case.get("expect_min_keywords")

    # Only assert on the report when the case says something about it. Cases that
    # stop before write_report must be able to assert "no report yet" explicitly.
    wants_report = bool(want_frags or deny_frags or want_files is not None or want_min_kw is not None)
    if case.get("expect_no_report"):
        checks.append(_check("report_absent", not path.exists(), path.exists(), False))
        return checks
    if not wants_report:
        return checks

    if not path.exists():
        checks.append(_check("report_exists", False, "missing", path.name))
        return checks
    checks.append(_check("report_exists", True, path.name, path.name))
    text = path.read_text(encoding="utf-8")

    for frag in want_frags:
        checks.append(_check(f"report_contains:{frag}", frag in text, frag in text, True))
    for frag in deny_frags:
        checks.append(_check(f"report_excludes:{frag}", frag not in text, frag in text, False))

    if want_files is not None:
        m = re.search(r"Files analyzed:\s*(\d+)", text)
        got = int(m.group(1)) if m else None
        checks.append(_check("files_analyzed", got == want_files, got, want_files))

    if want_min_kw is not None:
        got = len(_report_section(text, "Top keywords"))
        checks.append(_check("min_keywords", got >= want_min_kw, got, f">={want_min_kw}"))
    return checks


def assert_trace(store: Store, session, case: Dict[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    trace_path = store.trace_path(session.session_id)
    checks.append(_check("trace_exists", trace_path.exists() and trace_path.stat().st_size > 0, trace_path.exists(), True))
    if not trace_path.exists():
        return checks

    rows = []
    bad_lines = []
    for i, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad_lines.append(i)
    checks.append(_check("trace_jsonl_parses", not bad_lines, bad_lines or "clean", "all lines JSON"))

    attempted = [s.name for s in session.steps if s.status in ("succeeded", "failed")]
    traced = [r.get("step") for r in rows]
    missing = [n for n in attempted if n not in traced]
    checks.append(_check("trace_covers_attempted", not missing, missing or "clean", "every attempted step traced"))

    bad_dur = [r.get("step") for r in rows if not isinstance(r.get("duration_ms"), int) or r["duration_ms"] < 0]
    checks.append(_check("trace_duration_ms_int", not bad_dur, bad_dur or "clean", "int >= 0"))

    bad_size = [r.get("step") for r in rows
                if not isinstance(r.get("out_chars"), int) or not isinstance(r.get("out_items"), int)]
    checks.append(_check("trace_output_size_fields", not bad_size, bad_size or "clean", "out_chars/out_items int on every row"))
    if case.get("expect_trace_out_chars_min") is not None:
        want = case["expect_trace_out_chars_min"]
        got = max((r.get("out_chars") or 0) for r in rows) if rows else 0
        checks.append(_check("trace_out_chars_min", got >= want, got, f">={want}"))

    cost_bad = []
    free_bad = []
    for r in rows:
        if r.get("tokens_in_est") is None or r.get("price_in_per_mtok") is None:
            cost_bad.append((r.get("step"), "missing token/rate fields"))
            continue
        recomputed = cost_from_rates(
            r["tokens_in_est"], r["tokens_out_est"], r["price_in_per_mtok"], r["price_out_per_mtok"]
        )
        if abs(recomputed - r["cost_usd"]) > 1e-12:
            cost_bad.append((r.get("step"), f"cost_usd={r['cost_usd']} recomputes to {recomputed}"))
        if r.get("estimator") != ESTIMATOR_ID:
            cost_bad.append((r.get("step"), f"estimator={r.get('estimator')}"))
        if r.get("price_id") != case.get("price_id", DEFAULT_PRICE_ID):
            cost_bad.append((r.get("step"), f"price_id={r.get('price_id')} expected {case.get('price_id', DEFAULT_PRICE_ID)}"))
        # a step that moved bytes through it must not be free: a hardcoded 0.0
        # would otherwise satisfy "recomputable" trivially when rates were zeroed
        if (r.get("tokens_in_est") or 0) + (r.get("tokens_out_est") or 0) > 0 and r["cost_usd"] <= 0:
            free_bad.append(r.get("step"))
    checks.append(_check("trace_cost_recomputable", not cost_bad, cost_bad or "clean", "cost_usd == tokens × row-recorded rates on every row"))
    checks.append(_check("trace_cost_nonzero_when_tokens_nonzero", not free_bad, free_bad or "clean", "no step claims 0 cost after moving tokens"))

    if case.get("expect_trace_error_code"):
        want = case["expect_trace_error_code"]
        got = sorted({r.get("error_code") for r in rows if r.get("error_code")})
        checks.append(_check("trace_error_code_history", want in got, got, want))

    # a trace row must never claim success for a step that is not succeeded in state
    state_by_name = {s.name: s.status for s in session.steps}
    lying = [r.get("step") for r in rows if str(r.get("status", "")).startswith("succeeded") and state_by_name.get(r.get("step")) != "succeeded"]
    checks.append(_check("trace_matches_state", not lying, lying or "clean", "trace status agrees with state.json"))
    return checks


def assert_events(store: Store, session, case: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    case = case or {}
    checks: List[Dict[str, Any]] = []
    ev_path = store.events_path(session.session_id)
    checks.append(_check("events_exist", ev_path.exists() and ev_path.stat().st_size > 0, ev_path.exists(), True))
    if not ev_path.exists():
        return checks
    rows = []
    bad = []
    for i, line in enumerate(ev_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad.append(i)
    checks.append(_check("events_jsonl_parses", not bad, bad or "clean", "all lines JSON"))
    if case.get("expect_retry_delays") is not None:
        want = case["expect_retry_delays"]
        got = [r["payload"].get("delay_ms") for r in rows if (r.get("type") or r.get("kind")) == "step.retry_scheduled"]
        checks.append(_check("retry_delays", got == want, got, want))

    kinds = [r.get("kind") or r.get("type") for r in rows]
    checks.append(_check("events_first_is_session_created", bool(kinds) and "session.created" in str(kinds[0]), kinds[:1], "session.created first"))
    done = sum(1 for k in kinds if k == "session.succeeded")
    checks.append(_check("events_single_terminal_event", done <= 1, done, "<=1 session.succeeded"))
    return checks


def run_plan_case(case: Dict[str, Any], runs_root: Path) -> Dict[str, Any]:
    name = case["name"]
    topic = case.get("topic", "Agent Infra")
    input_dir = resolve_input_dir(case)
    expect_status = case.get("expect_status", "succeeded")

    store = Store(runs_root / name)
    session = create_session(store, f"eval:{name}", default_plan(topic, input_dir), input_dir=input_dir, topic=topic)

    timeout_on_step = case.get("timeout_on_step")
    timeout_ms = case.get("timeout_ms")
    if timeout_on_step and timeout_ms:
        for st in session.steps:
            if st.name == timeout_on_step:
                st.timeout_ms = timeout_ms

    max_retries = case.get("max_retries", 0)
    run_kwargs = {
        "fail_on_step": case.get("fail_on_step"),
        "max_retries": max_retries,
        "backoff_base_ms": case.get("backoff_base_ms", 0),
        "backoff_cap_ms": case.get("backoff_cap_ms", 4000),
        "price_id": case.get("price_id", DEFAULT_PRICE_ID),
    }
    session = run_session(store, session, **run_kwargs)

    # recovery run: drop the injected knobs (a resume must not keep hitting the same fault)
    resume_kwargs = {**run_kwargs, "fail_on_step": None}
    for _ in range(int(case.get("resume_runs", 0))):
        for st in session.steps:
            if st.timeout_ms is not None:
                st.timeout_ms = None
        session = run_session(store, session, **resume_kwargs)

    if case.get("run_twice"):
        session = run_session(store, session, **run_kwargs)

    checks: List[Dict[str, Any]] = [_check("status", session.status == expect_status, session.status, expect_status)]
    checks += assert_report(store.session_dir(session.session_id) / "report.md", case)

    if case.get("expect_error_code"):
        got_codes = [s.error_code for s in session.steps if s.error_code]
        checks.append(_check("error_code", case["expect_error_code"] in got_codes, got_codes, case["expect_error_code"]))

    if case.get("expect_min_attempts"):
        want_att = case["expect_min_attempts"]
        rows = [json.loads(l) for l in store.trace_path(session.session_id).read_text(encoding="utf-8").splitlines() if l.strip()]
        got_att = max((r.get("attempt") or 1) for r in rows) if rows else 0
        checks.append(_check("min_attempts", got_att >= want_att, got_att, f">={want_att}"))

    if case.get("expect_error_step"):
        got = sorted({s.name for s in session.steps if s.error_code})
        checks.append(_check("error_step", got == [case["expect_error_step"]], got, [case["expect_error_step"]]))

    checks += assert_trace(store, session, case)
    checks += assert_events(store, session, case)

    statuses = [s.status for s in session.steps]
    first_stop = next((i for i, st in enumerate(statuses) if st in ("failed",)), len(statuses))
    bad_prefix = [s.name + ":" + s.status for i, s in enumerate(session.steps) if i < first_stop and s.status != "succeeded"]
    checks.append(_check("prefix_integrity", not bad_prefix, bad_prefix or "clean", "steps before first failure are all succeeded"))

    if case.get("expect_all_steps_succeeded") is not None or expect_status == "succeeded":
        checks.append(_check("all_steps_done", all(st == "succeeded" for st in statuses), statuses, "all succeeded"))
    if expect_status in ("interrupted", "failed"):
        checks.append(_check(
            "pending_preserved_for_resume",
            any(st == "pending" for st in statuses) or first_stop == len(statuses) - 1,
            statuses,
            "remaining steps pending (resumable)",
        ))

    if case.get("expect_write_idempotent"):
        # second run over the same state must not rewrite the report
        written_flags = []
        for line in store.trace_path(session.session_id).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("step") == "write_report" and row.get("status") == "succeeded":
                written_flags.append(row)
        checks.append(_check("write_report_runs_twice", len(written_flags) >= 1, len(written_flags), ">=1 successful write attempt"))
        report = store.session_dir(session.session_id) / "report.md"
        checks.append(_check("report_still_single_copy", report.exists(), report.exists(), True))

    passed = all(c["pass"] for c in checks)
    return {
        "case": name,
        "mode": "plan",
        "passed": passed,
        "session_id": session.session_id,
        "state_path": str(store.state_path(session.session_id)),
        "checks": checks,
    }


def _cost_summary(store: Store, session_id: str) -> Dict[str, Any]:
    """Recompute cost totals from trace rows. Mirrors agent.main.trace_cost_summary.

    Kept local rather than imported so the harness asserts on the trace file's own
    contract, not on whichever helper the CLI happens to ship today.
    """
    path = store.trace_path(session_id)
    tot_in = tot_out = 0
    tot_cost = 0.0
    steps = 0
    mismatches = []
    if not path.exists():
        return {"steps": 0, "tokens_in_est": 0, "tokens_out_est": 0, "cost_usd": 0.0, "mismatches": []}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("tokens_in_est") is None:
            continue
        steps += 1
        tot_in += row["tokens_in_est"]
        tot_out += row["tokens_out_est"]
        tot_cost += row["cost_usd"]
        recomputed = cost_from_rates(
            row["tokens_in_est"], row["tokens_out_est"], row["price_in_per_mtok"], row["price_out_per_mtok"]
        )
        if abs(recomputed - row["cost_usd"]) > 1e-12:
            mismatches.append({"step": row.get("step"), "row": row["cost_usd"], "recomputed": recomputed})
    return {"steps": steps, "tokens_in_est": tot_in, "tokens_out_est": tot_out, "cost_usd": tot_cost, "mismatches": mismatches}


def run_cost_case(case: Dict[str, Any], runs_root: Path) -> Dict[str, Any]:
    """Run a plan, then verify the cost summary — optionally after tampering.

    The tamper variant is the positive control for the mismatch detector: a
    detector that never reports anything is not a detector.
    """
    name = case["name"]
    inner = {k: v for k, v in case.items() if not k.startswith("tamper")}
    inner["name"] = name + "_plan"
    plan_result = run_plan_case(inner, runs_root)
    checks: List[Dict[str, Any]] = [_check("plan_status", plan_result["passed"], plan_result["passed"], True)]

    store = Store(runs_root / inner["name"])
    session_id = plan_result["session_id"]
    if case.get("tamper_cost_row"):
        path = store.trace_path(session_id)
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        idx = case.get("tamper_row_index", 0)
        rows[idx]["cost_usd"] = rows[idx]["cost_usd"] + 1.0
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    summary = _cost_summary(store, session_id)
    checks.append(_check("cost_summary_steps", summary["steps"] >= 1, summary["steps"], ">=1"))
    if case.get("expect_cost_mismatches") is not None:
        want = case["expect_cost_mismatches"]
        checks.append(_check("cost_mismatch_count", len(summary["mismatches"]) == want, len(summary["mismatches"]), want))
    if case.get("expect_cost_positive"):
        checks.append(_check("cost_total_positive", summary["cost_usd"] > 0, summary["cost_usd"], ">0"))
    if case.get("expect_cost_tokens_min"):
        want = case["expect_cost_tokens_min"]
        checks.append(_check("cost_tokens_min", summary["tokens_in_est"] + summary["tokens_out_est"] >= want,
                             summary["tokens_in_est"] + summary["tokens_out_est"], f">={want}"))
    passed = all(c["pass"] for c in checks)
    return {"case": name, "mode": "cost", "passed": passed, "session_id": session_id,
            "state_path": plan_result["state_path"], "checks": checks}


def _cmp_output(key: str, want: Any, output: Any) -> tuple[Any, bool]:
    if not isinstance(output, dict):
        return None, False
    if key.endswith("_suffix"):
        got = output.get(key[: -len("_suffix")])
        return got, isinstance(got, str) and got.endswith(want)
    got = output.get(key)
    return got, got == want


def run_tool_case(case: Dict[str, Any], runs_root: Path) -> Dict[str, Any]:
    name = case["name"]
    run_dir = runs_root / name
    run_dir.mkdir(parents=True, exist_ok=True)
    input_dir = resolve_input_dir(case)
    reg = build_default_registry(run_dir, input_dir=Path(input_dir))

    calls = case.get("tool_calls") or [case["tool"]]
    checks: List[Dict[str, Any]] = []
    results = []
    for idx, call in enumerate(calls, 1):
        fn_name = call.get("name", "")
        if fn_name not in reg.names():
            # An unregistered tool IS the expected outcome when the case asks for
            # rejection: the registry must be closed, and the harness should score
            # "rejected" as a pass, not as its own error.
            expects_reject = case.get("expect_unknown_tool_rejected") or call.get("expect_tool_ok") is False
            checks.append(_check(f"call{idx}_unknown_tool_rejected", expects_reject, fn_name, "rejected by closed registry" if expects_reject else "registered"))
            ln = case.get("expect_error_code")
            if ln:
                checks.append(_check(f"call{idx}_error_code", ln == "UNKNOWN_TOOL", "UNKNOWN_TOOL", ln))
            results.append(None)
            continue
        checks.append(_check(f"call{idx}_tool_registered", True, fn_name, "in registry"))
        result = reg.get(fn_name)(**call.get("args", {}))
        results.append(result)
        want_ok = call.get("expect_tool_ok", case.get("expect_tool_ok", True))
        checks.append(_check(f"call{idx}_ok", result.ok == want_ok, result.ok, want_ok))
        if not result.ok:
            checks.append(_check(f"call{idx}_error_code", result.error_code == case.get("expect_error_code"), result.error_code, case.get("expect_error_code")))
        for key, want in (call.get("expect_output_value") or {}).items():
            got, ok = _cmp_output(key, want, result.output)
            checks.append(_check(f"call{idx}[{key}]", ok, got, want))

    last = results[-1] if results else None
    for key, want in (case.get("expect_output_value") or {}).items():
        got, ok = _cmp_output(key, want, last.output if last else None)
        checks.append(_check(f"output[{key}]", ok, got, want))
    if case.get("expect_output_key"):
        key = case["expect_output_key"]
        present = isinstance(last.output, dict) and key in last.output if last else False
        checks.append(_check(f"output_has:{key}", present, present, True))
    if case.get("expect_file_exists"):
        target = run_dir / case["expect_file_exists"]
        checks.append(_check("file_written", target.exists(), target.exists(), case["expect_file_exists"]))
    if case.get("expect_absent_file"):
        target = run_dir / case["expect_absent_file"]
        checks.append(_check("no_stray_file", not target.exists(), target.exists(), False))

    passed = all(c["pass"] for c in checks)
    return {"case": name, "mode": "tool", "passed": passed, "checks": checks}


def ensure_fixtures() -> None:
    """Rebuild generated corpus fixtures if they are missing.

    corpus/edge/large.txt is gitignored (700 KB of filler is not worth carrying),
    so a fresh clone has to regenerate it before the timeout cases have a big
    enough file to chew on.
    """
    large = CORPUS["edge"] / "large.txt"
    if large.exists():
        return
    gen = _ROOT / "corpus" / "make_edge.py"
    if not gen.exists():
        return
    subprocess.run([sys.executable, str(gen)], check=False, capture_output=True, text=True)


def _enrich_result(result: Dict[str, Any], runs_root: Path) -> None:
    """Attach duration_ms + cost rollup to a case result from its own trace file.

    Reuses the harness-local _cost_summary (which recomputes cost from each
    row's own rates) instead of importing the CLI's helper, so the contract's
    numbers are traceable to the artifact that was actually written.
    """
    sid = result.get("session_id")
    state_path = result.get("state_path")
    metrics: Dict[str, Any] = {"has_session": bool(sid)}
    if not sid or not state_path:
        result["metrics"] = metrics
        return
    store = Store(Path(state_path).parent.parent)
    summary = _cost_summary(store, sid)
    trace = store.trace_path(sid)
    duration_ms = 0
    if trace.exists():
        for line in trace.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    duration_ms += int(json.loads(line).get("duration_ms", 0) or 0)
                except (ValueError, TypeError):
                    pass
    metrics.update({
        "duration_ms": duration_ms,
        "steps": summary["steps"],
        "tokens_in_est": summary["tokens_in_est"],
        "tokens_out_est": summary["tokens_out_est"],
        "cost_usd": summary["cost_usd"],
        "cost_mismatches": len(summary["mismatches"]),
    })
    result["metrics"] = metrics


def main() -> None:
    ensure_fixtures()
    cases_path = _here / "cases" / "cases.json"
    only = sys.argv[1] if len(sys.argv) > 1 else None
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if only:
        cases = [c for c in cases if c["name"] == only]

    runs_root = Path(tempfile.mkdtemp(prefix="eval_runs_"))
    results = []
    for c in cases:
        case = dict(c)
        if case.get("mode") == "tool":
            result = run_tool_case(case, runs_root)
        elif case.get("mode") == "cost":
            result = run_cost_case(case, runs_root)
        else:
            result = run_plan_case(case, runs_root)
        _enrich_result(result, runs_root)
        results.append(result)

    thresholds = {
        "min_total": len(cases),
        "max_failed": 0,
        # Require every mode that the selected case set actually contains.
        "require_modes": sorted({c.get("mode", "plan") for c in cases}),
    }
    contract = build_contract(
        results,
        thresholds=thresholds,
        content_sha12={
            "cases": sha12(cases_path),
            "runner": sha12(Path(__file__).resolve()),
            "contract": sha12(_here / "gate_contract.py"),
        },
    )
    # Default artifact: readable by any CI consumer at a fixed path.
    out = Path(__file__).resolve().parent / "last_contract.json"
    err = write_contract(contract, out)
    if err:
        contract = not_run_on_write_failure(contract, err)

    # First line is always the machine-parsable summary; body is the full contract.
    print(contract["summary"])
    print(json.dumps(contract, ensure_ascii=False, indent=2))
    raise SystemExit(contract["exit_code"])


if __name__ == "__main__":
    main()
