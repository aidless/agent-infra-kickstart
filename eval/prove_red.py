from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_here = Path(__file__).resolve().parent
_root = _here.parent


def run_suite(cwd: Path) -> int:
    return subprocess.run(
        [sys.executable, str(cwd / "eval" / "run_eval.py")],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    ).returncode


def main() -> None:
    """Prove the eval gate can go RED (非空性反证).

    1) Copy the project into a temp dir.
    2) Baseline: copied tree must be GREEN (exit 0) — otherwise the gate is broken
       for an unrelated reason and the red test would be meaningless.
    3) Inject a real violation into the renderer (drop the per-file section, which
       happy_path asserts on) and assert the suite exits non-zero.
    """
    work = Path(tempfile.mkdtemp(prefix="prove_red_"))
    shutil.copytree(_root / "agent", work / "agent")
    shutil.copytree(_root / "eval", work / "eval")
    shutil.copytree(_root / "sample_input", work / "sample_input")
    shutil.copytree(_root / "corpus", work / "corpus")

    base_rc = run_suite(work)
    print(f"baseline: exit={base_rc} (expect 0)")
    if base_rc != 0:
        print("FAIL: baseline of the copied tree is red; red-proof is not interpretable")
        raise SystemExit(1)

    runner_py = work / "agent" / "runner.py"
    src = runner_py.read_text(encoding="utf-8")
    loop = """    for f in extraction.get("files", []):
        hits = f.get("topic_hits") or {}
        hit_str = ", ".join([f"{k}={v}" for k, v in hits.items()]) if hits else "n/a"
        lines.append(f"- {Path(f.get('path','')).name}: lines={f.get('lines')} chars={f.get('chars')} words={f.get('words')} topic_hits=({hit_str})")
"""
    if loop not in src:
        print("FAIL: per-file loop anchor not found")
        raise SystemExit(1)
    injected = src.replace(loop, "    # INJECTED VIOLATION: per-file section removed\n")
    runner_py.write_text(injected, encoding="utf-8")
    red_rc = run_suite(work)
    print(f"[1/5] injected report-section removal: exit={red_rc} (expect non-zero)")
    if red_rc == 0:
        print("FAIL: gate stayed green when the report section was removed")
        raise SystemExit(1)
    runner_py.write_text(src, encoding="utf-8")

    # Injection 2: strip the deadline plumbing. The timeout case must notice,
    # which proves the TIMEOUT assertions are actually wired to the runner and
    # not merely asserted on a code path nothing reaches.
    tools_py = work / "agent" / "tools.py"
    tsrc = tools_py.read_text(encoding="utf-8")
    guard = """    dl = _deadline.get()
    if dl is not None and time.monotonic() > dl:
        raise ToolTimeout(f"step exceeded timeout budget")
"""
    if guard not in tsrc:
        print("FAIL: deadline guard anchor not found")
        raise SystemExit(1)
    tools_py.write_text(tsrc.replace(guard, "    return\n"), encoding="utf-8")
    red2_rc = run_suite(work)
    print(f"[2/5] injected deadline-guard removal: exit={red2_rc} (expect non-zero)")
    tools_py.write_text(tsrc, encoding="utf-8")

    # Injection 3: remove the resume no-op guard. The "run_twice" case must then
    # see a second session.succeeded event and the terminal-event assertion must fail.
    runner_src = runner_py.read_text(encoding="utf-8")
    noop = """    if session.status == "succeeded" and all(s.status == "succeeded" for s in session.steps):
        return session
"""
    if noop not in runner_src:
        print("FAIL: resume no-op guard anchor not found")
        raise SystemExit(1)
    runner_py.write_text(runner_src.replace(noop, ""), encoding="utf-8")
    red3_rc = run_suite(work)
    print(f"[3/5] injected resume-noop removal: exit={red3_rc} (expect non-zero)")
    runner_py.write_text(runner_src, encoding="utf-8")

    # Injection 4: break cost recomputability by pricing every row out of a table
    # entry that disagrees with compute_cost. The trace_cost_recomputable assertion
    # exists precisely so a row cannot carry a number nobody can re-derive.
    cost_py = work / "agent" / "cost.py"
    csrc = cost_py.read_text(encoding="utf-8")
    price_anchor = '"fixture-standard": {"in_per_mtok": 3.00, "out_per_mtok": 15.00},'
    if price_anchor not in csrc:
        print("FAIL: pricing table anchor not found")
        raise SystemExit(1)
    cost_py.write_text(csrc.replace(price_anchor, '"fixture-standard": {"in_per_mtok": 0.0, "out_per_mtok": 0.0},'), encoding="utf-8")
    red4_rc = run_suite(work)
    print(f"[4/5] injected price-table edit: exit={red4_rc} (expect non-zero)")
    cost_py.write_text(csrc, encoding="utf-8")

    # Injection 5: flatten the backoff schedule. retry_backoff_schedule_exponential
    # pins [200, 400, 400]; a constant delay must fail it.
    bsrc = runner_py.read_text(encoding="utf-8")
    backoff_anchor = "    raw = base_ms * (2 ** (attempt - 1))"
    if backoff_anchor not in bsrc:
        print("FAIL: backoff anchor not found")
        raise SystemExit(1)
    runner_py.write_text(bsrc.replace(backoff_anchor, "    raw = base_ms"), encoding="utf-8")
    red5_rc = run_suite(work)
    print(f"[5/5] injected constant backoff: exit={red5_rc} (expect non-zero)")
    runner_py.write_text(bsrc, encoding="utf-8")

    shutil.rmtree(work, ignore_errors=True)
    failures = []
    if red2_rc == 0:
        failures.append("timeout guard disabled")
    if red3_rc == 0:
        failures.append("resume no-op guard removed")
    if red4_rc == 0:
        failures.append("price table disagrees with recorded cost")
    if red5_rc == 0:
        failures.append("backoff schedule flattened")
    if failures:
        print("FAIL: gate stayed green under: " + ", ".join(failures))
        raise SystemExit(1)
    print("OK: gate goes red under all 5 injected violations")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
