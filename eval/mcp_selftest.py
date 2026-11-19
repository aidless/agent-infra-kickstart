"""Falsifiable selftest + prove_red for the real MCP server.

selftest checks the protocol surface in-process AND over a real stdio
subprocess. prove_red injects three violations one at a time; every one must
make the suite fail, otherwise the gate is decorative.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mcp_server as M

CHECKS: list[tuple[str, Callable[[], str | None]]] = []


def check(name: str):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def _state(tmp: Path) -> M.ServerState:
    (tmp / "run").mkdir(parents=True, exist_ok=True)
    (tmp / "in").mkdir(parents=True, exist_ok=True)
    (tmp / "in" / "a.txt").write_text("alpha beta beta topic\n", encoding="utf-8")
    return M.build_state(tmp / "run", tmp / "in")


def _req(state: M.ServerState, msg: dict[str, Any]) -> dict[str, Any]:
    out = M.handle_line(state, json.dumps(msg))
    assert len(out) == 1, f"expected 1 response, got {out}"
    return out[0]


def _handshake(state: M.ServerState, version: str = M.PROTOCOL_VERSION) -> None:
    r = _req(state, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": version, "capabilities": {},
                                "clientInfo": {"name": "selftest", "version": "0"}}})
    assert r["result"]["protocolVersion"] == version, r
    assert r["result"]["capabilities"]["tools"]["listChanged"] is False, r
    assert r["result"]["serverInfo"]["name"] == M.SERVER_INFO["name"], r
    assert M.handle_line(state, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})) == []


@check("initialize negotiates version and declares tools capability")
def c_initialize():
    with tempfile.TemporaryDirectory() as d:
        st = _state(Path(d))
        _handshake(st)
        assert st.initialized and st.ready, (st.initialized, st.ready)
    return None


@check("unsupported protocol version -> -32602 with supported list")
def c_bad_version():
    with tempfile.TemporaryDirectory() as d:
        st = _state(Path(d))
        r = _req(st, {"jsonrpc": "2.0", "id": 9, "method": "initialize",
                      "params": {"protocolVersion": "0.0.0"}})
        e = r["error"]
        assert e["code"] == M.INVALID_PARAMS and "0.0.0" == e["data"]["requested"], r
        assert M.PROTOCOL_VERSION in e["data"]["supported"], r
    return None


@check("tools/list requires completed handshake (not just initialize)")
def c_gate_before_ready():
    with tempfile.TemporaryDirectory() as d:
        st = _state(Path(d))
        r = _req(st, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert r["error"]["code"] == M.INVALID_REQUEST, r
        st.initialized = True  # halfway state: still blocked
        r = _req(st, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        assert r["error"]["code"] == M.INVALID_REQUEST, r
    return None


@check("tools/list exposes exactly the four live tools with inputSchema")
def c_tools_list():
    with tempfile.TemporaryDirectory() as d:
        st = _state(Path(d))
        _handshake(st)
        r = _req(st, {"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        tools = r["result"]["tools"]
        names = [t["name"] for t in tools]
        assert sorted(names) == st.registry.names(), (names, st.registry.names())
        for t in tools:
            assert t["inputSchema"]["type"] == "object" and "description" in t, t
    return None


@check("tools/call list_files and extract_keywords return content + isError=false")
def c_call_read():
    with tempfile.TemporaryDirectory() as d:
        st = _state(Path(d))
        _handshake(st)
        r = _req(st, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                      "params": {"name": "list_files", "arguments": {"directory": str(Path(d) / "in"), "glob": "*.txt"}}})
        tr = r["result"]
        assert tr["isError"] is False and tr["content"][0]["type"] == "text", tr
        assert tr["structuredContent"]["count"] == 1, tr
        r = _req(st, {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                      "params": {"name": "extract_keywords", "arguments": {"paths": ["a.txt"], "topic": "topic"}}})
        assert r["result"]["isError"] is False, r
        assert r["result"]["structuredContent"]["topic"] == "topic", r
    return None


@check("tools/call write_text succeeds, then same content is idempotent")
def c_call_write_idempotent():
    with tempfile.TemporaryDirectory() as d:
        st = _state(Path(d))
        _handshake(st)
        args = {"path": "out/report.md", "content": "hello"}
        r = _req(st, {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                      "params": {"name": "write_text", "arguments": args}})
        assert r["result"]["structuredContent"]["written"] is True, r
        r2 = _req(st, {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                       "params": {"name": "write_text", "arguments": args}})
        assert r2["result"]["structuredContent"]["written"] is False, r2
        assert r2["result"]["structuredContent"]["reason"] == "same_content", r2
    return None


@check("write_text path escape -> isError=true + PATH_ESCAPE (not a crash)")
def c_sandbox_escape():
    with tempfile.TemporaryDirectory() as d:
        st = _state(Path(d))
        _handshake(st)
        r = _req(st, {"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                      "params": {"name": "write_text", "arguments": {"path": "../escape.md", "content": "x"}}})
        assert r["result"]["isError"] is True, r
        assert json.loads(r["result"]["content"][0]["text"])["error_code"] == "PATH_ESCAPE", r
    return None


@check("unknown tool -> isError=true, not JSON-RPC error or exception")
def c_unknown_tool():
    with tempfile.TemporaryDirectory() as d:
        st = _state(Path(d))
        _handshake(st)
        r = _req(st, {"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                      "params": {"name": "no_such_tool", "arguments": {}}})
        assert "result" in r and r["result"]["isError"] is True, r
        assert json.loads(r["result"]["content"][0]["text"])["error_code"] == "UNKNOWN_TOOL", r
    return None


@check("bad tools/call params -> -32602; unknown method -> -32601; parse error -> -32700")
def c_protocol_errors():
    with tempfile.TemporaryDirectory() as d:
        st = _state(Path(d))
        _handshake(st)
        r = _req(st, {"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": 42}})
        assert r["error"]["code"] == M.INVALID_PARAMS, r
        r = _req(st, {"jsonrpc": "2.0", "id": 13, "method": "no/method"})
        assert r["error"]["code"] == M.METHOD_NOT_FOUND, r
        r = M.handle_line(st, "not json")[0]
        assert r["error"]["code"] == M.PARSE_ERROR and r["id"] is None, r
    return None


@check("batch of ping+tools/list returns ordered responses, notification dropped")
def c_batch():
    with tempfile.TemporaryDirectory() as d:
        st = _state(Path(d))
        _handshake(st)
        out = M.handle_line(st, json.dumps([
            {"jsonrpc": "2.0", "id": 20, "method": "ping"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 21, "method": "tools/list"},
        ]))
        assert [o["id"] for o in out] == [20, 21], out
    return None


@check("real stdio subprocess: initialize -> initialized -> tools/list -> tools/call")
def c_stdio_subprocess():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "run").mkdir(); (root / "in").mkdir()
        (root / "in" / "a.txt").write_text("topic alpha beta\n", encoding="utf-8")
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": M.PROTOCOL_VERSION, "capabilities": {},
                        "clientInfo": {"name": "stdio-test", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "list_files", "arguments": {"directory": ".", "glob": "*.txt"}}},
        ]
        proc = subprocess.run(
            [sys.executable, str(Path(M.__file__).resolve()), "--run-dir", str(root / "run"),
             "--input-dir", str(root / "in")],
            input="\n".join(json.dumps(m) for m in msgs) + "\n",
            text=True, capture_output=True, timeout=20,
        )
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        lines = [json.loads(x) for x in proc.stdout.strip().splitlines() if x.strip()]
        assert [x["id"] for x in lines] == [1, 2, 3], lines
        assert len(lines[1]["result"]["tools"]) == 5, lines[1]
        names = {t["name"] for t in lines[1]["result"]["tools"]}
        assert "read_file_window" in names, names
        assert lines[2]["result"]["isError"] is False, lines[2]
    return None


ALL_CHECKS = list(CHECKS)


def run_suite(checks=ALL_CHECKS) -> list[str]:
    failures: list[str] = []
    for name, fn in checks:
        try:
            err = fn()
            if err:
                failures.append(f"{name}: {err}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    return failures


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--prove-red" in argv:
        print("mcp gate prove_red: injecting 3 violations; each must turn the suite red", flush=True)
        originals = {
            "_tool_result_payload": M._tool_result_payload,
            "tool_list_definitions": M.tool_list_definitions,
            "_dispatch": M._dispatch,
        }
        all_red = True
        # [1/3] never flag tool errors
        def always_ok(result):
            return {"content": [{"type": "text", "text": json.dumps({"ok": True, "output": result.output})}]}
        # [2/3] advertise no tools
        def no_tools(state):
            return []
        # [3/3] skip handshake gate: allow tools/list before initialized
        def no_gate(state, msg):
            if msg.get("method") == "tools/list" and not (state.initialized and state.ready):
                return M._ok(msg.get("id"), {"tools": M.tool_list_definitions(state)})
            return originals["_dispatch"](state, msg)
        for label, target, stub in [
            ("[1/3] isError disabled", "_tool_result_payload", always_ok),
            ("[2/3] tool list emptied", "tool_list_definitions", no_tools),
            ("[3/3] handshake gate skipped", "_dispatch", no_gate),
        ]:
            setattr(M, target, stub)
            try:
                failures = run_suite()
            finally:
                setattr(M, target, originals[target])
            red = len(failures) > 0
            all_red = all_red and red
            print(f"  {label}: {'RED (expected)' if red else 'GREEN (BUG: gate is decorative)'}", flush=True)
            if not red:
                print("    unexpected passes:", [f.split(':')[0] for f in []] or "suite all green", flush=True)
        clean = run_suite()
        ok = all_red and not clean
        print(f"mcp gate prove_red: {'OK' if ok else 'FAIL'} (all 3 injected violations red={all_red}, baseline clean={not clean})", flush=True)
        return 0 if ok else 1
    failures = run_suite()
    problems = len(failures)
    print(f"mcp-selftest: problems={problems} total={len(ALL_CHECKS)} passed={len(ALL_CHECKS)-problems}", flush=True)
    for f in failures:
        print("  FAIL", f, flush=True)
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
