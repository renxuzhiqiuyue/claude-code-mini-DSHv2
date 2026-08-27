"""会话列表、子代理与 jsonl 路径解析（给 Web / CLI）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.memory import paths, runtime
from harness.memory.constants import SESSION_JSONL
from harness.memory.consolidate import session_needs_compress
from harness.memory.files import is_session_consolidated
from harness.memory.jsonl import iter_session_dirs, load_session_view, read_jsonl_events


def list_planner_sessions(*, limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in iter_session_dirs()[:limit]:
        view = load_session_view(d)
        title = ""
        for m in view.get("messages") or []:
            if isinstance(m, dict) and "HumanMessage" in m:
                title = str(m["HumanMessage"] or "")[:80]
                break
        sub_n = sum(
            1
            for e in (view.get("events") or [])
            if isinstance(e, dict) and e.get("type") == "subagent/start"
        )
        out.append(
            {
                "name": d.name,
                "id": d.name,
                "path": f".memory/{d.name}",
                "started_at": view.get("started_at") or "",
                "source": view.get("source") or "",
                "title": title or d.name,
                "subagents": sub_n,
                "format": "jsonl",
                "consolidated": is_session_consolidated(d.name),
                "message_count": len(view.get("messages") or []),
                "needs_compress": session_needs_compress(d.name),
            }
        )
    return out


def list_session_subagents(session_name: str) -> list[dict[str, Any]]:
    """列出某会话下的 Solver 子代理（事件 + solver/ 目录）。"""
    name = (session_name or "").strip().replace("\\", "/").lstrip("/")
    if not name or ".." in name or "/" in name:
        raise ValueError("非法会话名")
    folder = paths.MEMORY_DIR / name
    if not folder.is_dir():
        raise FileNotFoundError(name)

    by_path: dict[str, dict[str, Any]] = {}
    events = read_jsonl_events(folder / SESSION_JSONL)
    last_desc = ""
    for ev in events:
        if not isinstance(ev, dict):
            continue
        t = ev.get("type")
        if t == "tool/call" and ev.get("name") in ("solve_task", "task"):
            args = ev.get("args") or {}
            if isinstance(args, dict):
                last_desc = str(args.get("description") or args.get("prompt") or args.get("task") or "")
        if t == "subagent/start":
            path = str(ev.get("path") or "")
            if not path:
                continue
            by_path[path] = {
                "path": path,
                "name": ev.get("name") or "solver",
                "title": (last_desc[:80] if last_desc else "") or path.rsplit("/", 1)[-1],
                "desc": last_desc,
                "start_ts": ev.get("ts") or "",
                "end_ts": "",
                "summary": "",
                "done": False,
            }
        if t == "subagent/end":
            path = str(ev.get("path") or "")
            if not path:
                continue
            row = by_path.get(path) or {
                "path": path,
                "name": ev.get("name") or "solver",
                "title": path.rsplit("/", 1)[-1],
                "desc": "",
                "start_ts": "",
            }
            row["end_ts"] = ev.get("ts") or ""
            row["summary"] = str(ev.get("summary") or "")[:2000]
            row["done"] = True
            if not row.get("desc") and row["summary"]:
                row["desc"] = row["summary"]
            if row["summary"] and (not row.get("title") or row["title"] == path.rsplit("/", 1)[-1]):
                row["title"] = row["summary"][:80]
            by_path[path] = row

    solver_dir = folder / "solver"
    if solver_dir.is_dir():
        for f in sorted(solver_dir.glob("*.jsonl")):
            rel = f"solver/{f.name}"
            if rel in by_path:
                continue
            meta = {}
            for ev in read_jsonl_events(f)[:5]:
                if isinstance(ev, dict) and ev.get("type") == "session/meta":
                    meta = ev
                    break
                if isinstance(ev, dict) and ev.get("type") == "user/message":
                    meta = {"title_hint": ev.get("text") or ""}
                    break
            title_hint = str(meta.get("title_hint") or meta.get("id") or f.stem)
            by_path[rel] = {
                "path": rel,
                "name": "solver",
                "title": title_hint[:80],
                "desc": title_hint,
                "start_ts": str(meta.get("ts") or meta.get("started_at") or ""),
                "end_ts": "",
                "summary": "",
                "done": True,
            }

    return list(by_path.values())


def resolve_session_jsonl(name: str) -> Path:
    """解析会话或子代理 jsonl 路径。

    - session_xxx → .memory/session_xxx/session.jsonl
    - session_xxx/solver/yyy.jsonl
    - solver/yyy.jsonl（相对当前父会话）
    """
    name = (name or "").strip().replace("\\", "/").lstrip("/")
    if not name or ".." in name:
        raise ValueError("非法会话名")

    if name.endswith(SESSION_JSONL) and name.count("/") == 1:
        folder, _ = name.split("/", 1)
        path = paths.MEMORY_DIR / folder / SESSION_JSONL
        if path.exists():
            return path

    if "/solver/" in name:
        parts = name.split("/")
        if len(parts) == 3:
            path = paths.MEMORY_DIR / parts[0] / "solver" / parts[2]
            if path.exists():
                return path

    if name.startswith("solver/") and runtime.current_session_dir is not None:
        path = runtime.current_session_dir / name
        if path.exists():
            return path

    if name.startswith("session_") and "/" not in name:
        path = paths.MEMORY_DIR / name / SESSION_JSONL
        if path.exists():
            return path
        for d in iter_session_dirs():
            cand = d / "solver" / name
            if cand.exists():
                return cand
            if not name.endswith(".jsonl"):
                cand = d / "solver" / f"{name}.jsonl"
                if cand.exists():
                    return cand

    if name.endswith(".jsonl") and runtime.current_session_dir is not None:
        cand = runtime.current_session_dir / "solver" / name
        if cand.exists():
            return cand

    raise FileNotFoundError(name)


def get_session_events(name: str) -> list[dict]:
    path = resolve_session_jsonl(name)
    return read_jsonl_events(path)
