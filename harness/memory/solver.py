"""Solver 子会话：写在父会话目录 solver/ 下。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from harness.memory import runtime
from harness.memory.files import ensure_memory_files
from harness.memory.jsonl import append_jsonl_event, event_fingerprint, msg_to_events, note_event_ts, read_jsonl_events, write_jsonl_meta
from harness.memory.session import append_parent_event


def start_solver_session(*, parent_session: str | None = None) -> Path:
    if runtime.current_session_dir is None:
        raise RuntimeError("无父会话，无法启动 Solver")
    ensure_memory_files()
    ts = datetime.now()
    slug = ts.strftime("%Y%m%d_%H%M%S_%f")
    solver_dir = runtime.current_session_dir / "solver"
    solver_dir.mkdir(parents=True, exist_ok=True)
    path = solver_dir / f"session_{slug}.jsonl"
    parent = parent_session or runtime.current_session_dir.name
    runtime.solver_session_meta = {
        "source": "solver",
        "started_at": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "parent_session": parent,
        "id": path.stem,
        "origin": "subagent",
    }
    write_jsonl_meta(path, runtime.solver_session_meta)
    runtime.solver_session = path
    append_parent_event(
        {
            "type": "subagent/start",
            "name": "solver",
            "path": f"solver/{path.name}",
            "parent_session": parent,
        }
    )
    print(f"  \033[90m[solver-memory] .memory/{runtime.current_session_dir.name}/solver/{path.name}\033[0m")
    return path


def sync_solver_session_messages(messages: list, *, reason: str = "") -> None:
    if runtime.solver_session is None:
        start_solver_session()
    assert runtime.solver_session is not None
    tag = f" ({reason})" if reason else ""
    new_events: list[dict] = []
    for msg in messages:
        new_events.extend(msg_to_events(msg))
    existing = read_jsonl_events(runtime.solver_session)
    for e in existing:
        if isinstance(e, dict):
            note_event_ts(runtime.solver_session, e.get("ts"))
    seen = {event_fingerprint(e) for e in existing}
    added = 0
    for ev in new_events:
        fp = event_fingerprint(ev)
        if fp in seen:
            continue
        append_jsonl_event(runtime.solver_session, ev)
        seen.add(fp)
        added += 1
    if added:
        print(f"  \033[90m[solver-memory] 会话已写入 +{added} 条{tag}\033[0m")


def end_solver_session(*, summary: str = "") -> None:
    if runtime.solver_session is not None:
        append_parent_event(
            {
                "type": "subagent/end",
                "name": "solver",
                "path": f"solver/{runtime.solver_session.name}",
                "summary": (summary or "")[:2000],
            }
        )
        print(f"  \033[90m[solver-memory] 结束: {runtime.solver_session.name}\033[0m")
    runtime.solver_session = None
    runtime.solver_session_meta = {}


def current_solver_session_name() -> str:
    return runtime.solver_session.name if runtime.solver_session else "（尚无 Solver 会话）"
