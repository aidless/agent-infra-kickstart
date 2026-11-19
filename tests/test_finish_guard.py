"""finish_guard 的非空性反证与正常路径（harness 改造 1+2 的验收判据）。

判据来自 notes/2026-11-18-harness改造清单-prestop-verifier.md：
  · 注入「直接 finish、工作树干净」必须被拦，且 observation 含 EMPTY_DIFF
  · 注入「有真实 diff 的 finish」必须放行，rc=0
  · 三条负向（产物空 / 编译失败 / 验证命令失败）+ 一条正向
两边都跑才算通过；只做正向 = 空门。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.finish_guard import (  # noqa: E402
    empty_diff_guard,
    prestop_compile_check,
    prestop_verify,
)
from agent.runner import create_session, default_plan, run_session  # noqa: E402
from agent.state import Step, Store  # noqa: E402


def _tmp(tmp_path: Path, name: str) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_empty_diff_rejected(tmp_path):
    """负向 1：run_dir 无产物且无写入声明 → EMPTY_DIFF（门必须能红）。"""
    run_dir = _tmp(tmp_path, "run")
    g = empty_diff_guard(run_dir)
    assert g.ok is False
    assert g.code == "EMPTY_DIFF"


def test_empty_diff_allowed_when_written(tmp_path):
    """负向 1 的反证：有 written=True 声明即放行。"""
    run_dir = _tmp(tmp_path, "run")
    g = empty_diff_guard(run_dir, produced_paths=["report.md"])
    assert g.ok is True
    assert g.checked["produced_paths"] == 1


def test_empty_diff_artifact_counted(tmp_path):
    """正向：run_dir 里真有产物文件 → 放行。"""
    run_dir = _tmp(tmp_path, "run")
    (run_dir / "report.md").write_text("# Report\nhello\n", encoding="utf-8")
    g = empty_diff_guard(run_dir)
    assert g.ok is True
    assert g.checked["artifacts"] == 1


def test_empty_diff_analytics_not_counted(tmp_path):
    """账本类文件（.state.json / events.jsonl / trace.jsonl）不算产物。"""
    run_dir = _tmp(tmp_path, "run")
    for name in (".state.json", "events.jsonl", "trace.jsonl"):
        (run_dir / name).write_text("{}\n", encoding="utf-8")
    g = empty_diff_guard(run_dir)
    assert g.ok is False
    assert g.checked["artifacts"] == 0


def test_empty_diff_allow_no_artifact_exemptions(tmp_path):
    """任务类型显式豁免：纯问答 session 可用 allow_no_artifact=True。"""
    run_dir = _tmp(tmp_path, "run")
    g = empty_diff_guard(run_dir, allow_no_artifact=True)
    assert g.ok is True


def test_compile_check_detects_bad_py(tmp_path):
    """负向 2：语法坏的 .py 必须被拦，且报 VERIFY_COMPILE_FAILED。"""
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n    pass\n", encoding="utf-8")
    g = prestop_compile_check([bad])
    assert g.ok is False
    assert g.code == "VERIFY_COMPILE_FAILED"


def test_compile_check_ok(tmp_path):
    good = tmp_path / "good.py"
    good.write_text("X = 1\n", encoding="utf-8")
    g = prestop_compile_check([good])
    assert g.ok is True


def test_compile_check_missing_file(tmp_path):
    g = prestop_compile_check([tmp_path / "nope.py"])
    assert g.ok is False
    assert g.code == "VERIFY_MISSING_FILE"


def test_prestop_verify_verify_cmd_fails(tmp_path):
    """负向 3：调用方声明的验证命令跑不过必须拦。"""
    run_dir = _tmp(tmp_path, "run")
    (run_dir / "report.md").write_text("ok", encoding="utf-8")
    g = prestop_verify(run_dir, verify_cmd="exit 3")
    assert g.ok is False
    assert g.code == "VERIFY_CMD_FAILED"
    assert g.checked["verify_cmd"]["returncode"] == 3


def test_prestop_verify_passes(tmp_path):
    run_dir = _tmp(tmp_path, "run")
    (run_dir / "report.md").write_text("ok", encoding="utf-8")
    g = prestop_verify(run_dir, verify_cmd="true")
    assert g.ok is True
    assert g.checked["artifact"]["ok"] is True
    assert g.checked["compile"]["checked"]["files"] == 0
    assert g.checked["verify_cmd"]["returncode"] == 0


def test_prestop_verify_missing_artifact_beats_verify_cmd(tmp_path):
    """产物为空时必须拦，即使验证命令能过（顺序：先产物后命令）。"""
    run_dir = _tmp(tmp_path, "run")
    g = prestop_verify(run_dir, verify_cmd="true")
    assert g.ok is False
    assert g.code == "EMPTY_DIFF"


def test_runner_blocks_empty_finish(tmp_path):
    """集成：session 跑完但无任何产物 → 不记 succeeded，记 blocked_by_guard。"""
    run_dir = _tmp(tmp_path, "run")
    input_dir = _tmp(tmp_path, "sample_input")
    (input_dir / "a.txt").write_text("hello agent\n", encoding="utf-8")
    store = Store(_tmp(tmp_path, "state"))
    # 空目录 plan：只列文件、不写报告 —— 模拟「工作树干净」的 finish
    session = create_session(store, goal="no artifact", steps=[
        Step(step_id="s1", name="list_inputs", tool="list_files",
             args={"directory": str(input_dir), "glob": "*"})
    ])
    out = run_session(store, session)
    assert out.status == "failed"
    events = store.events_path(session.session_id).read_text(encoding="utf-8")
    assert "session.blocked_by_guard" in events
    assert "EMPTY_DIFF" in events


def test_runner_passes_with_artifact(tmp_path):
    """集成：正常产出报告 → 放行，记 succeeded。"""
    input_dir = _tmp(tmp_path, "sample_input")
    (input_dir / "a.txt").write_text("hello agent infra\n", encoding="utf-8")
    store = Store(_tmp(tmp_path, "state"))
    session = create_session(store, goal="report", input_dir=str(input_dir),
                             steps=default_plan("Agent Infra", input_dir=str(input_dir)))
    out = run_session(store, session)
    assert out.status == "succeeded"
    events = store.events_path(session.session_id).read_text(encoding="utf-8")
    assert "session.succeeded" in events
    assert "finish_guard.checked" in events


def test_runner_guard_event_row(tmp_path):
    """终态前 guard 自己必须落一行 event（append-only 审计，且不污染成本 trace）。"""
    input_dir = _tmp(tmp_path, "sample_input")
    (input_dir / "a.txt").write_text("hello agent infra\n", encoding="utf-8")
    store = Store(_tmp(tmp_path, "state"))
    session = create_session(store, goal="report", input_dir=str(input_dir),
                             steps=default_plan("Agent Infra", input_dir=str(input_dir)))
    run_session(store, session)
    events = store.events_path(session.session_id).read_text(encoding="utf-8")
    assert "finish_guard.checked" in events
    trace = store.trace_path(session.session_id).read_text(encoding="utf-8")
    assert "finish_guard" not in trace


# ── 改造 3：窗口化文件视图（read_file_window）────────────────────────────
from agent.tools import build_default_registry  # noqa: E402


def _registry(tmp_path):
    run = _tmp(tmp_path, "run3")
    return build_default_registry(run), run


def test_window_returns_requested_page_with_line_numbers(tmp_path):
    reg, run = _registry(tmp_path)
    (run / "doc.txt").write_text("\n".join(f"line-{i}" for i in range(1, 11)), encoding="utf-8")
    r = reg.get("read_file_window")("doc.txt", start_line=3, max_lines=4)
    assert r.ok is True
    assert r.output["returned_lines"] == 4
    assert r.output["total_lines"] == 10
    assert r.output["start_line"] == 3
    assert "     3 | line-3" in r.output["content"]
    assert r.output["next_start"] == 7


def test_window_last_page_has_no_next(tmp_path):
    reg, run = _registry(tmp_path)
    (run / "doc.txt").write_text("a\nb\nc\n", encoding="utf-8")
    r = reg.get("read_file_window")("doc.txt", start_line=3, max_lines=5)
    assert r.ok is True
    assert r.output["returned_lines"] == 1
    assert r.output["next_start"] is None


def test_window_truncates_by_chars_and_flags_it(tmp_path):
    reg, run = _registry(tmp_path)
    (run / "doc.txt").write_text("x" * 500, encoding="utf-8")
    r = reg.get("read_file_window")("doc.txt", max_lines=10, max_chars=100)
    assert r.ok is True
    assert r.output["truncated"] is True
    assert r.output["chars"] == 100


def test_window_rejects_oversized_params(tmp_path):
    """服务端硬上限：调用方调大参数必须被拒，不能绕过。"""
    reg, run = _registry(tmp_path)
    (run / "doc.txt").write_text("x\n", encoding="utf-8")
    tool = reg.get("read_file_window")
    assert tool("doc.txt", max_lines=100000).ok is False
    assert tool("doc.txt", max_chars=1000000).ok is False
    assert tool("doc.txt", start_line=0).ok is False


def test_window_rejects_missing_file(tmp_path):
    reg, run = _registry(tmp_path)
    r = reg.get("read_file_window")("nope.txt")
    assert r.ok is False
    assert r.error_code == "NOT_FOUND"
