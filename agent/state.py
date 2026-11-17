from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class Step:
    step_id: str
    name: str
    tool: str
    args: Dict[str, Any]
    status: str = "pending"  # pending|running|succeeded|failed|skipped
    output: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_ms: Optional[int] = None
    idempotency_key: Optional[str] = None
    timeout_ms: Optional[int] = None  # per-step budget; None = session default


@dataclass
class Session:
    session_id: str
    goal: str
    status: str = "running"  # running|succeeded|failed|interrupted
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    input_dir: Optional[str] = None
    topic: Optional[str] = None
    steps: List[Step] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["steps"] = [asdict(s) for s in self.steps]
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Session":
        steps = [Step(**s) for s in d.get("steps", [])]
        data = {k: v for k, v in d.items() if k != "steps"}
        return Session(steps=steps, **data)


class Store:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def session_dir(self, session_id: str) -> Path:
        p = self.base_dir / session_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def state_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "state.json"

    def events_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "events.jsonl"

    def trace_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "trace.jsonl"

    def save(self, session: Session) -> None:
        session.updated_at = now_iso()
        path = self.state_path(session.session_id)
        path.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, session_id: str) -> Session:
        path = self.state_path(session_id)
        return Session.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def append_event(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        event = {
            "event_id": new_id("evt"),
            "type": event_type,
            "ts": now_iso(),
            "payload": payload,
        }
        with self.events_path(session_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def append_trace(self, session_id: str, record: Dict[str, Any]) -> None:
        rec = {"ts": now_iso(), **record}
        with self.trace_path(session_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
