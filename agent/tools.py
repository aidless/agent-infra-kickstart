from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List


class ToolTimeout(Exception):
    """Raised cooperatively inside long tool loops when the step deadline passes."""


_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar("deadline", default=None)
_TICK_EVERY = 200  # check the clock every N loop iterations, not every iteration


def set_deadline(seconds: float | None):
    if seconds is None:
        return _deadline.set(None)
    return _deadline.set(time.monotonic() + seconds)


def clear_deadline(token) -> None:
    _deadline.reset(token)


def _tick(i: int) -> None:
    """Cooperative timeout check: tools must call this inside their loops."""
    if i % _TICK_EVERY:
        return
    dl = _deadline.get()
    if dl is not None and time.monotonic() > dl:
        raise ToolTimeout(f"step exceeded timeout budget")


def measure_output(output: Any) -> Dict[str, int]:
    """Cheap, dependency-free size proxy for a step output.

    Trace rows carry out_chars / out_items so a later pass can chart cost per step
    without re-reading every tool's payload shape. This is a proxy, not a token
    count: it deliberately says nothing about model spend.
    """
    if output is None:
        return {"out_chars": 0, "out_items": 0}
    text = json.dumps(output, ensure_ascii=False, default=str) if not isinstance(output, str) else output
    items = 0
    if isinstance(output, dict):
        items = len(output)
    elif isinstance(output, (list, tuple, set)):
        items = len(output)
    return {"out_chars": len(text), "out_items": items}


RETRYABLE_ERROR_CODES = frozenset({"TIMEOUT", "EXCEPTION", "LIST_ERROR", "EXTRACT_ERROR", "WRITE_ERROR", "SUMMARIZE_ERROR"})


@dataclass
class ToolResult:
    ok: bool
    output: Any = None
    error: str | None = None
    error_code: str | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Callable[..., ToolResult]] = {}

    def register(self, name: str, fn: Callable[..., ToolResult]) -> None:
        self._tools[name] = fn

    def get(self, name: str) -> Callable[..., ToolResult]:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def names(self):
        return sorted(self._tools.keys())


def _resolve_inside(base: Path, rel: str) -> Path:
    target = (base / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    base_r = base.resolve()
    if target != base_r and base_r not in target.parents:
        raise ValueError("path escapes run dir")
    return target


def _resolve_readable(run_dir: Path, input_dir: Path | None, path: str) -> Path:
    p = Path(path)
    candidates = []
    if p.is_absolute():
        candidates.append(p.resolve())
    else:
        candidates.append((run_dir / p).resolve())
        if input_dir:
            candidates.append((input_dir / p).resolve())
    for c in candidates:
        if c.exists():
            # allow reads inside run_dir or input_dir or cwd-relative resolved existing
            return c
    # default to run_dir relative for clearer error
    return (run_dir / p).resolve()


def build_default_registry(run_dir: Path, input_dir: Path | None = None) -> ToolRegistry:
    reg = ToolRegistry()

    def list_files(directory: str = ".", glob: str = "*", limit: int = 200) -> ToolResult:
        try:
            _tick(0)
            base: Path | None
            if Path(directory).is_absolute():
                base = Path(directory).resolve()
            else:
                candidates = [Path(directory).resolve()]
                if input_dir:
                    candidates.append((input_dir / directory).resolve())
                candidates.append((run_dir / directory).resolve())
                base = next((c for c in candidates if c.exists() and c.is_dir()), None)
            if base is None or not base.exists() or not base.is_dir():
                return ToolResult(False, error=f"directory not found: {directory}", error_code="NOT_FOUND")
            files = []
            for i, p in enumerate(sorted(base.rglob(glob))):
                _tick(i)
                if p.is_file():
                    try:
                        rel = str(p.relative_to(base))
                    except ValueError:
                        rel = str(p)
                    files.append({"path": str(p), "rel": rel, "bytes": p.stat().st_size})
                if len(files) >= limit:
                    break
            return ToolResult(True, {"directory": str(base), "count": len(files), "files": files})
        except ToolTimeout as e:
            return ToolResult(False, error=str(e), error_code="TIMEOUT")
        except Exception as e:  # noqa: BLE001
            return ToolResult(False, error=repr(e), error_code="LIST_ERROR")

    def extract_keywords(paths: List[str], topic: str = "", top_n: int = 10) -> ToolResult:
        try:
            _tick(0)
            if not isinstance(paths, list) or not paths:
                return ToolResult(False, error="paths must be a non-empty list", error_code="BAD_INPUT")
            stop = {
                "the","and","or","to","of","in","a","for","is","on","with","by","an","be","as",
                "are","this","that","it","from","can","we","our","需要","一个","以及","进行","可以","用于",
            }
            total = Counter()
            per_file = []
            topic_terms = [t for t in re.split(r"\W+", topic.lower()) if t]
            for i, raw in enumerate(paths):
                _tick(i)
                p = _resolve_readable(run_dir, input_dir, raw)
                if not p.exists() or not p.is_file():
                    return ToolResult(False, error=f"file not found: {raw}", error_code="NOT_FOUND")
                text = p.read_text(encoding="utf-8", errors="replace")
                tokens = []
                for j, chunk in enumerate(re.split(r"[^A-Za-z0-9_\u4e00-\u9fff]+", text.lower())):
                    _tick(j)
                    if chunk and chunk not in stop and len(chunk) > 1:
                        tokens.append(chunk)
                c = Counter(tokens)
                total.update(c)
                hits = {t: text.lower().count(t) for t in topic_terms} if topic_terms else {}
                per_file.append({
                    "path": str(p),
                    "lines": len(text.splitlines()),
                    "chars": len(text),
                    "words": len(tokens),
                    "topic_hits": hits,
                    "top5": c.most_common(5),
                })
            return ToolResult(True, {
                "files": per_file,
                "total_files": len(per_file),
                "top_keywords": total.most_common(max(1, top_n)),
                "topic": topic,
            })
        except ToolTimeout as e:
            return ToolResult(False, error=str(e), error_code="TIMEOUT")
        except Exception as e:  # noqa: BLE001
            return ToolResult(False, error=repr(e), error_code="EXTRACT_ERROR")

    def write_text(path: str, content: str) -> ToolResult:
        try:
            _tick(0)
            target = _resolve_inside(run_dir, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                existing = target.read_text(encoding="utf-8")
                if existing == content:
                    return ToolResult(True, {"path": str(target), "written": False, "reason": "same_content", "idempotent": True})
            target.write_text(content, encoding="utf-8")
            checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
            return ToolResult(True, {"path": str(target), "written": True, "bytes": len(content.encode("utf-8")), "checksum": checksum, "idempotent": False})
        except ValueError as e:
            return ToolResult(False, error=str(e), error_code="PATH_ESCAPE")
        except ToolTimeout as e:
            return ToolResult(False, error=str(e), error_code="TIMEOUT")
        except Exception as e:  # noqa: BLE001
            return ToolResult(False, error=repr(e), error_code="WRITE_ERROR")

    def summarize_text(path: str, preview_chars: int = 160) -> ToolResult:
        try:
            _tick(0)
            target = _resolve_readable(run_dir, input_dir, path)
            if not target.exists():
                return ToolResult(False, error=f"file not found: {path}", error_code="NOT_FOUND")
            text = target.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            words = len(text.split())
            preview = text[: max(0, preview_chars)]
            return ToolResult(True, {
                "path": str(target),
                "chars": len(text),
                "lines": len(lines),
                "words": words,
                "preview": preview,
            })
        except ToolTimeout as e:
            return ToolResult(False, error=str(e), error_code="TIMEOUT")
        except Exception as e:  # noqa: BLE001
            return ToolResult(False, error=repr(e), error_code="SUMMARIZE_ERROR")

    reg.register("list_files", list_files)
    reg.register("extract_keywords", extract_keywords)
    reg.register("write_text", write_text)
    reg.register("summarize_text", summarize_text)
    return reg
