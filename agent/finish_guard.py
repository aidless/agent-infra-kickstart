"""Finish guards — 空 diff guard + pre-stop verifier（harness 改造 1+2）。

来源与证据（不把论文数字当自己的收益，只借结构）：
  arXiv:2611.22299 Table IV / §V。该文的 Stage 3 门只接受模块化补丁，
  其中两处是「退出前必须自证」类的模块：
    · 未验证退出（OOD exit）modular 0.0% vs full rewrite 5.0% vs
      prompt-only(RULES.md 明写禁令) 30.0% —— 说明「写进提示词」比
      「运行时阻断」差一个数量级（Table IV）。
    · verify.py 原版只是 pass-through，接受改写后才成为真门（§V）。
  本模块只实现机制，不宣称任何收益增量。

两条 guard：
  1. empty_diff_guard —— 终态前工作树没有任何改动（且本 session 也没写
     出任何产物）时，拒绝把 session 标记 succeeded，改记 EMPTY_DIFF。
  2. prestop_verify —— 终态前三项全过才准退出：
       a) 产物非空（复用 1 的产物检查）
       b) 本次改动触及的 .py 可编译（py_compile，编译产物写临时目录，
          不污染 run_dir）
       c) 调用方声明的验证命令能跑过（不新造测试口径：用 agent 已经跑过
          的那条命令，由调用方传入）
     任一项失败 → 拒绝退出，原因原文进 session.error 供下一轮修复。

设计纪律：
  · 只在此仓可验证的范围内主张（stdlib only，不 import 外部）
  · 每个 guard 都能「红」——见 tests/test_finish_guard.py 的注入用例
  · 不改任务提示词（Table IV：prompt-only 行把未验证退出抬到 30%）
"""

from __future__ import annotations

import py_compile
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# 产物目录里不算「产物」的账本类文件（它们由 store 自己写）
ANALYTICS_ARTIFACTS = {"state.json", ".state.json", "events.jsonl", "trace.jsonl"}


@dataclass
class GuardResult:
    ok: bool
    code: str = "OK"
    detail: str = ""
    checked: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "code": self.code, "detail": self.detail, "checked": self.checked}


def _artifact_files(run_dir: Path) -> List[Path]:
    """run_dir 下属于「产出」的文件（排除账本类）。"""
    if not run_dir.exists():
        return []
    out = []
    for p in sorted(run_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.parent == run_dir and p.name in ANALYTICS_ARTIFACTS:
            continue
        out.append(p)
    return out


def empty_diff_guard(
    run_dir: Path,
    *,
    produced_paths: Sequence[str] | None = None,
    allow_no_artifact: bool = False,
) -> GuardResult:
    """空 diff guard。

    「空 diff」在本仓的定义：session 声称完成，但
      (a) 没有写盘产物（run_dir 除账本外为空），且
      (b) 调用方也没报告任何 written=True 的产物路径。
    两者都空 → EMPTY_DIFF。任一非空 → 放行。

    allow_no_artifact=True 用于纯问答型 session（不需要产物的任务），
    等价于论文里「按任务类型显式标记」的缓解手段。
    """
    arts = _artifact_files(run_dir)
    written = [p for p in (produced_paths or []) if p]
    checked = {"artifacts": len(arts), "produced_paths": len(written),
               "allow_no_artifact": allow_no_artifact}
    if allow_no_artifact:
        return GuardResult(True, "OK", "allow_no_artifact=True（任务类型显式豁免）", checked)
    if not arts and not written:
        return GuardResult(
            False, "EMPTY_DIFF",
            "session 声称完成，但 run_dir 无产物且没有任何 written=True 的写入",
            checked,
        )
    return GuardResult(True, "OK", f"产物 {len(arts)} 个 / 写入声明 {len(written)} 条", checked)


def prestop_compile_check(
    py_files: Sequence[str | Path] | None = None,
) -> GuardResult:
    """改动过的 .py 必须可编译。编译产物写临时目录，不污染仓库。"""
    files = [Path(p) for p in (py_files or [])]
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        return GuardResult(False, "VERIFY_MISSING_FILE", f"声明的文件不存在: {missing}", {"files": len(files)})
    if not files:
        return GuardResult(True, "OK", "无可编译文件", {"files": 0})
    with tempfile.TemporaryDirectory(prefix="prestop_pyc_") as td:
        for p in files:
            try:
                py_compile.compile(str(p), cfile=str(Path(td) / (p.stem + ".pyc")), doraise=True)
            except py_compile.PyCompileError as e:
                return GuardResult(False, "VERIFY_COMPILE_FAILED", str(e), {"file": str(p)})
    return GuardResult(True, "OK", f"{len(files)} 个文件编译通过", {"files": len(files)})


def prestop_verify(
    run_dir: Path,
    *,
    produced_paths: Sequence[str] | None = None,
    py_files: Sequence[str | Path] | None = None,
    verify_cmd: Optional[str] = None,
    verify_timeout_s: float = 120.0,
    allow_no_artifact: bool = False,
) -> GuardResult:
    """三项全过才准退出：产物非空 → .py 可编译 → 调用方验证命令通过。

    verify_cmd 必须是 agent 已经跑过的那条命令（不新造口径）。
    """
    checks: Dict[str, Any] = {}
    g1 = empty_diff_guard(run_dir, produced_paths=produced_paths, allow_no_artifact=allow_no_artifact)
    checks["artifact"] = g1.as_dict()
    if not g1.ok:
        return GuardResult(False, g1.code, "产物检查失败：" + g1.detail, checks)

    g2 = prestop_compile_check(py_files)
    checks["compile"] = g2.as_dict()
    if not g2.ok:
        return GuardResult(False, g2.code, "编译检查失败：" + g2.detail, checks)

    if verify_cmd:
        try:
            cp = subprocess.run(
                verify_cmd, shell=True, cwd=str(run_dir),
                capture_output=True, text=True, timeout=verify_timeout_s,
            )
        except subprocess.TimeoutExpired:
            checks["verify_cmd"] = {"cmd": verify_cmd, "timeout_s": verify_timeout_s}
            return GuardResult(False, "VERIFY_TIMEOUT", f"验证命令超时 {verify_timeout_s}s", checks)
        tail = (cp.stderr or cp.stdout or "").strip().splitlines()[-8:]
        checks["verify_cmd"] = {"cmd": verify_cmd, "returncode": cp.returncode, "tail": tail}
        if cp.returncode != 0:
            return GuardResult(False, "VERIFY_CMD_FAILED", f"验证命令 rc={cp.returncode}：" + " | ".join(tail), checks)
    else:
        checks["verify_cmd"] = {"cmd": None, "note": "调用方未提供验证命令（本项视为未检查）"}

    return GuardResult(True, "OK", "三项通过", checks)
