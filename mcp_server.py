"""Minimal real MCP server (spec 2025-06-18) over stdio, zero third-party deps.

Implements the parts of the protocol that matter for an actual handshake and
real tool calls: initialize / version negotiation / initialized notification /
tools/list / tools/call / ping, JSON-RPC 2.0 error codes, stdio framing.

Exposes the four kickstart tools from agent.tools as MCP tools. Everything
except the stdio loop is a pure function so tests can drive it in-process,
and a subprocess smoke test exercises the real byte-level transport.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agent.tools import ToolResult, build_default_registry

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_VERSIONS = (PROTOCOL_VERSION, "2024-11-05")
SERVER_INFO = {"name": "agent-infra-kickstart-mcp", "version": "0.1.0"}

# JSON-RPC 2.0 standard codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_files",
        "title": "List files under a directory",
        "description": "List files under a directory, with glob and result limit. Path resolution is sandboxed to the run dir or the configured input dir.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to scan."},
                "glob": {"type": "string", "description": "Glob pattern, e.g. '*.txt'."},
                "limit": {"type": "integer", "minimum": 1, "description": "Max number of files returned."},
            },
            "required": [],
        },
    },
    {
        "name": "extract_keywords",
        "title": "Extract keywords from files",
        "description": "Extract top keywords across files and per-file statistics, optionally counting topic terms.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Files to read."},
                "topic": {"type": "string", "description": "Optional topic whose terms are counted."},
                "top_n": {"type": "integer", "minimum": 1, "description": "Number of top keywords."},
            },
            "required": ["paths"],
        },
    },
    {
        "name": "write_text",
        "title": "Write text into the run dir",
        "description": "Write UTF-8 text into the run dir. Idempotent on same content. Paths escaping the run dir are rejected with PATH_ESCAPE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Destination path, relative to the run dir."},
                "content": {"type": "string", "description": "UTF-8 content to write."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "summarize_text",
        "title": "Summarize a readable file",
        "description": "Return character/line/word counts and a short preview of a readable file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File to summarize."},
                "preview_chars": {"type": "integer", "minimum": 0, "description": "Preview length in characters."},
            },
            "required": ["path"],
        },
    },
]


@dataclass
class ServerState:
    registry: Any
    version: str | None = None
    initialized: bool = False
    ready: bool = False
    call_log: list[str] = field(default_factory=list)


def tool_list_definitions(state: ServerState) -> list[dict[str, Any]]:
    """Return MCP tool definitions, cross-checked against the live registry."""
    live = set(state.registry.names())
    defs = [t for t in TOOL_DEFINITIONS if t["name"] in live]
    return defs


def _tool_result_payload(result: ToolResult) -> dict[str, Any]:
    """Map a kickstart ToolResult to an MCP ToolResult (spec 2025-06-18)."""
    text = json.dumps(
        {"ok": result.ok, "output": result.output, "error": result.error, "error_code": result.error_code},
        ensure_ascii=False,
    )
    payload: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": not result.ok,
    }
    if result.ok and isinstance(result.output, dict):
        payload["structuredContent"] = result.output
    return payload


def call_tool(state: ServerState, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    state.call_log.append(name)
    if name not in state.registry.names():
        return _tool_result_payload(ToolResult(False, error=f"unknown tool: {name}", error_code="UNKNOWN_TOOL"))
    fn = state.registry.get(name)
    try:
        result = fn(**arguments)
    except TypeError as exc:
        result = ToolResult(False, error=f"bad arguments: {exc}", error_code="BAD_ARGUMENTS")
    except Exception as exc:  # noqa: BLE001 - a tool crash must surface as isError, never kill the server
        result = ToolResult(False, error=repr(exc), error_code="EXCEPTION")
    return _tool_result_payload(result)


def _ok(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def _dispatch(state: ServerState, msg: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch one request. Notifications return None (no response per JSON-RPC)."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _err(msg.get("id") if isinstance(msg, dict) else None, INVALID_REQUEST, "Invalid Request")
    method = msg.get("method")
    msg_id = msg.get("id")
    is_notification = "id" not in msg

    if method == "initialize":
        params = msg.get("params") or {}
        requested = params.get("protocolVersion")
        if requested not in SUPPORTED_VERSIONS:
            return _err(msg_id, INVALID_PARAMS, "Unsupported protocol version",
                        {"supported": list(SUPPORTED_VERSIONS), "requested": requested})
        state.version = requested
        state.initialized = True
        state.ready = False
        return _ok(msg_id, {
            "protocolVersion": requested,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": dict(SERVER_INFO),
            "instructions": "Four local tools; write_text is sandboxed to the run dir.",
        })

    if method == "notifications/initialized":
        if not state.initialized:
            return None if is_notification else _err(msg_id, INVALID_REQUEST, "initialize first")
        state.ready = True
        return None

    if method == "ping":
        return _ok(msg_id, {}) if not is_notification else None

    # Every other method requires a completed handshake.
    if not state.initialized or not state.ready:
        return _err(msg_id, INVALID_REQUEST, "initialize and notifications/initialized required first")

    if method == "tools/list":
        return _ok(msg_id, {"tools": tool_list_definitions(state)})

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _err(msg_id, INVALID_PARAMS, "tools/call needs name:string and arguments:object")
        return _ok(msg_id, call_tool(state, name, arguments))

    return _err(msg_id, METHOD_NOT_FOUND, "Method not found")


def handle_line(state: ServerState, raw: str) -> list[dict[str, Any]]:
    """Handle one stdio line. Returns JSON-RPC responses (empty for notifications)."""
    try:
        msg = json.loads(raw)
    except (ValueError, TypeError):
        return [_err(None, PARSE_ERROR, "Parse error")]
    if isinstance(msg, list):  # JSON-RPC batch: preserve order, drop notification slots
        out: list[dict[str, Any]] = []
        for item in msg:
            resp = _dispatch(state, item)
            if resp is not None:
                out.append(resp)
        return out
    resp = _dispatch(state, msg)
    return [resp] if resp is not None else []


def serve(state: ServerState, stream_in=None, stream_out=None) -> None:
    """stdio transport: one JSON message per line, stdout carries protocol only."""
    stream_in = stream_in or sys.stdin
    stream_out = stream_out or sys.stdout
    for raw in stream_in:
        if not raw.strip():
            continue
        for resp in handle_line(state, raw):
            stream_out.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stream_out.flush()


def build_state(run_dir: Path, input_dir: Path | None = None) -> ServerState:
    return ServerState(registry=build_default_registry(Path(run_dir).resolve(),
                                                       Path(input_dir).resolve() if input_dir else None))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MCP server (stdio) exposing kickstart tools")
    ap.add_argument("--run-dir", required=True, help="Writable run dir (sandbox root for write_text)")
    ap.add_argument("--input-dir", default=None, help="Optional read-only input dir")
    args = ap.parse_args(argv)
    state = build_state(Path(args.run_dir), Path(args.input_dir) if args.input_dir else None)
    serve(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
