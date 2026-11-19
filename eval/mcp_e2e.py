"""eval/mcp_e2e.py — 真 client 经 stdio 驱动 MCP server 跑完整 4 步业务流程。

与 mcp_selftest（协议层 11 检查）互补：这里验业务可用性——
client 是编排者，MCP 是工具层，4 步跨步传参（list_files→extract_keywords→write_text→summarize_text）。
断言统一走 content[0].text 的 JSON 信封 {ok,output,error,error_code}（成败都有，最稳）；
成功且 output 为 dict 时顺带钉死 structuredContent == output（spec 字段）。
12 项检查；--prove-red 把 step3 期望改成 written=False（必红）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server.py"


def call(proc, method, params=None, msg_id=None, notify=False):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if not notify:
        msg["id"] = msg_id
    proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    if notify:
        return None
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout")
        resp = json.loads(line)
        if "id" in resp:
            return resp


def envelope(resp):
    """从 MCP tools/call 响应取 JSON 信封 {ok,output,error,error_code}。"""
    text = resp["result"]["content"][0]["text"]
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    prove_red = "--prove-red" in argv
    problems: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"  ok {name}")
        else:
            print(f"  FAIL {name} {detail}")
            problems.append(name)

    with tempfile.TemporaryDirectory() as td:
        run = Path(td) / "run"
        inp = Path(td) / "in"
        run.mkdir()
        inp.mkdir()
        (inp / "doc1.txt").write_text("agent harness eval gate mcp sandbox trace replay", encoding="utf-8")
        (inp / "doc2.txt").write_text("eval gate regression benchmark dataset", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--run-dir", str(run), "--input-dir", str(inp)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
        )
        try:
            # 1 initialize 版本协商
            r = call(proc, "initialize",
                     {"protocolVersion": "2025-06-18", "capabilities": {},
                      "clientInfo": {"name": "e2e", "version": "0"}}, 1)
            res = r.get("result", {})
            check("initialize 协商", res.get("protocolVersion") == "2025-06-18"
                  and res.get("serverInfo", {}).get("name") == "agent-infra-kickstart-mcp", str(r)[:160])
            # 2 initialized 通知
            call(proc, "notifications/initialized", notify=True)
            # 3 tools/list
            r = call(proc, "tools/list", {}, 2)
            names = sorted(t["name"] for t in r.get("result", {}).get("tools", []))
            check("tools/list 5 工具", names == ["extract_keywords", "list_files", "read_file_window",
                                                 "summarize_text", "write_text"], str(names))
            # 4 step1 list_files
            r = call(proc, "tools/call", {"name": "list_files", "arguments": {"directory": str(inp)}}, 3)
            env = envelope(r)
            sc = r.get("result", {}).get("structuredContent")
            check("step1 list_files", env["ok"] is True and env["output"]["count"] == 2
                  and sc == env["output"], f"env={env} sc_keys={list(sc) if isinstance(sc, dict) else sc}")
            paths = [f["path"] for f in env["output"]["files"]]
            # 5 step2 extract_keywords
            r = call(proc, "tools/call", {"name": "extract_keywords",
                                          "arguments": {"paths": paths, "topic": "eval"}}, 4)
            env = envelope(r)
            check("step2 extract_keywords", env["ok"] is True and len(env["output"].get("top_keywords", [])) > 0,
                  str(env)[:160])
            # 6 step3 write_text
            content = "# report\nkeywords: eval gate\nfiles: " + ", ".join(p.split("/")[-1] for p in paths) + "\n"
            r = call(proc, "tools/call", {"name": "write_text",
                                          "arguments": {"path": "report.md", "content": content}}, 5)
            env = envelope(r)
            want_written = False if prove_red else True
            check("step3 write_text written", env["ok"] is True and env["output"].get("written") == want_written
                  and (run / "report.md").exists(), str(env)[:160])
            # 7 step4 summarize_text
            r = call(proc, "tools/call", {"name": "summarize_text", "arguments": {"path": "report.md"}}, 6)
            env = envelope(r)
            check("step4 summarize_text", env["ok"] is True and env["output"].get("chars") == (len(content)),
                  str(env)[:160])
            # 8 read_file_window 分页
            r = call(proc, "tools/call", {"name": "read_file_window",
                                          "arguments": {"path": "report.md", "start_line": 1, "max_lines": 2}}, 7)
            env = envelope(r)
            check("read_file_window 分页", env["ok"] is True and env["output"].get("total_lines") == 3
                  and env["output"].get("returned_lines") == 2, str(env)[:160])
            # 9 幂等写
            r = call(proc, "tools/call", {"name": "write_text",
                                          "arguments": {"path": "report.md", "content": content}}, 8)
            env = envelope(r)
            check("幂等写 same_content", env["ok"] is True and env["output"].get("written") is False
                  and env["output"].get("reason") == "same_content", str(env)[:160])
            # 10 沙盒逃逸
            r = call(proc, "tools/call", {"name": "write_text",
                                          "arguments": {"path": "../escape.md", "content": "x"}}, 9)
            env = envelope(r)
            is_err = r.get("result", {}).get("isError") is True
            check("沙盒逃逸 PATH_ESCAPE", env["ok"] is False and env.get("error_code") == "PATH_ESCAPE" and is_err,
                  f"env={env} isError={is_err}")
            # 11 report 内容
            txt = (run / "report.md").read_text(encoding="utf-8")
            check("report 内容含关键词", "eval gate" in txt and "doc1.txt" in txt, txt[:80])
            # 12 未知工具
            r = call(proc, "tools/call", {"name": "no_such_tool", "arguments": {}}, 10)
            env = envelope(r)
            is_err = r.get("result", {}).get("isError") is True
            check("未知工具 UNKNOWN_TOOL", env["ok"] is False and env.get("error_code") == "UNKNOWN_TOOL" and is_err,
                  f"env={env} isError={is_err}")
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    total = 12
    print(f"mcp_e2e: problems={len(problems)} total={total} passed={total - len(problems)}")
    if problems:
        print("FAIL:", problems)
        return 1
    print("OK: real client drove the full 4-step business flow over stdio MCP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
