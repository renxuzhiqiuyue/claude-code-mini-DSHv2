"""Web 入口：FastAPI + 静态页（对话 / 轨迹 JSONL），共用 agents.build_agent()。

启动：
  python -m serve.web_server
  python -m serve.web_server --host 0.0.0.0 --port 8765
  uvicorn serve.web_server:app --host 127.0.0.1 --port 8765

会话在浏览器内选择：新建或打开 `.memory/session_*/`。
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Iterator

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("MINI_CC_NONINTERACTIVE", "1")

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field

from agents.agent import build_agent
from harness import config as cfg
from harness.config import MEMORY_DIR, ROOT, SKILLS_DIR, ensure_runtime_dirs, set_output_dir
from harness.memory import (
    compress_session,
    consolidate_session,
    create_new_session,
    current_session_log_text,
    current_session_name,
    get_session_events,
    list_planner_sessions,
    list_session_subagents,
    resume_session,
    session_needs_compress,
    session_started,
)
from harness.permission import bind_approver, reset_approver

WEB_DIR = Path(__file__).resolve().parent / "web"
PERMISSION_TIMEOUT_SEC = 300

_agent = None
_agent_lock = threading.Lock()
_pending_approvals: dict[str, dict[str, Any]] = {}
_pending_lock = threading.Lock()
_new_session_lock = threading.Lock()


def _ensure_boot(output_dir: str | None = None) -> None:
    """只准备目录；不自动创建会话（由前端选择）。"""
    global _agent
    if output_dir is not None:
        set_output_dir(output_dir)
        with _agent_lock:
            _agent = None
    elif cfg.OUTPUT_DIR is None or not str(cfg.OUTPUT_DIR):
        set_output_dir(os.environ.get("OUTPUT_DIR") or ".output")
    ensure_runtime_dirs()


def _require_session() -> None:
    if not session_started():
        raise HTTPException(409, "尚未选择会话：请先新建或打开会话")


def _reset_agent() -> None:
    global _agent
    with _agent_lock:
        _agent = None


def _get_agent():
    global _agent
    _require_session()
    with _agent_lock:
        if _agent is None:
            _agent = build_agent()
        return _agent


def _visible_roots() -> dict[str, Path]:
    """左栏工作区：仅当前 OUTPUT_DIR（默认 .output）。"""
    out_name = cfg.OUTPUT_DIR.name or ".output"
    return {out_name: cfg.OUTPUT_DIR.resolve()}


def _resolve_visible(rel: str) -> Path:
    raw = (rel or "").strip().lstrip("/")
    if not raw or ".." in Path(raw).parts:
        raise HTTPException(400, "非法路径")
    parts = Path(raw).parts
    roots = _visible_roots()
    root_key = parts[0]
    if root_key not in roots:
        # 兼容前端用 .output / output 别名
        if root_key in (".output", "output") and cfg.OUTPUT_DIR.name in roots:
            root_key = cfg.OUTPUT_DIR.name
        else:
            raise HTTPException(403, f"不可见根目录: {parts[0]}")
    base = roots[root_key]
    target = (base / Path(*parts[1:])).resolve() if len(parts) > 1 else base
    if not str(target).startswith(str(base)):
        raise HTTPException(403, "路径逃逸")
    return target


_TREE_BLOCKLIST = frozenset({
    "skills",
    ".skills",
    "memory",
    ".memory",
    ".MEMORY",
    "MEMORY.md",
    "__pycache__",
    ".venv",
    "node_modules",
})


def _tree_name_allowed(name: str) -> bool:
    if not name or name.startswith("."):
        return False
    if name in _TREE_BLOCKLIST or name.lower() in ("skills", "memory"):
        return False
    return True


def _tree_node(path: Path, rel: str, max_depth: int, depth: int = 0) -> dict[str, Any]:
    node: dict[str, Any] = {
        "name": path.name or rel,
        "path": rel.replace("\\", "/"),
        "type": "dir" if path.is_dir() else "file",
    }
    if path.is_dir() and depth < max_depth:
        children = []
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            entries = []
        for child in entries:
            if not _tree_name_allowed(child.name):
                continue
            child_rel = f"{rel}/{child.name}" if rel else child.name
            children.append(_tree_node(child, child_rel, max_depth, depth + 1))
        node["children"] = children
    return node


app = FastAPI(title="Claude-code-mini Web", version="0.5.0")


@app.on_event("startup")
def _startup() -> None:
    _ensure_boot()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str | None = None


class SettingsRequest(BaseModel):
    output_dir: str = Field(..., min_length=1)


class PermissionDecision(BaseModel):
    request_id: str = Field(..., min_length=1)
    allow: bool


@app.get("/api/health")
def api_health() -> dict:
    return {
        "ok": True,
        "output_dir": str(cfg.OUTPUT_DIR),
        "session": current_session_name() if session_started() else None,
        "session_ready": session_started(),
        "thread_id": cfg.THREAD_ID,
    }


@app.get("/api/settings")
def api_get_settings() -> dict:
    return {
        "output_dir": str(cfg.OUTPUT_DIR),
        "output_dir_name": cfg.OUTPUT_DIR.name,
        "memory_dir": str(MEMORY_DIR),
        "skills_dir": str(SKILLS_DIR),
        "root": str(ROOT),
        "session": current_session_name() if session_started() else None,
        "session_ready": session_started(),
        "thread_id": cfg.THREAD_ID,
    }


@app.post("/api/settings")
def api_set_settings(body: SettingsRequest) -> dict:
    _ensure_boot(output_dir=body.output_dir)
    return api_get_settings()


@app.get("/api/sessions")
def api_sessions(limit: int = Query(40, ge=1, le=200)) -> dict:
    _ensure_boot()
    return {
        "current": current_session_name() if session_started() else None,
        "session_ready": session_started(),
        "sessions": list_planner_sessions(limit=limit),
    }


@app.post("/api/session/new")
def api_session_new() -> dict:
    if not _new_session_lock.acquire(blocking=False):
        raise HTTPException(409, "正在创建会话，请稍候")
    try:
        _ensure_boot()
        create_new_session(source="web")
        _reset_agent()
        return {
            "ok": True,
            "session": current_session_name(),
            "thread_id": cfg.THREAD_ID,
            "session_ready": True,
        }
    finally:
        _new_session_lock.release()


class SessionOpenRequest(BaseModel):
    name: str = Field(..., min_length=1)
    consolidate: bool = False
    compress: bool = False


class SessionConsolidateRequest(BaseModel):
    name: str = Field(..., min_length=1)


@app.post("/api/session/consolidate")
def api_session_consolidate(body: SessionConsolidateRequest) -> dict:
    """将会话轨迹总结写入 MEMORY.md。"""
    _ensure_boot()
    result = consolidate_session(body.name.strip())
    if not result.get("ok") and "不存在" in str(result.get("message") or ""):
        raise HTTPException(404, result["message"])
    if not result.get("ok") and "非法" in str(result.get("message") or ""):
        raise HTTPException(400, result["message"])
    return result


@app.post("/api/session/open")
def api_session_open(body: SessionOpenRequest) -> dict:
    _ensure_boot()
    name = body.name.strip()
    consolidate_result = None
    compress_result = None
    if body.consolidate:
        consolidate_result = consolidate_session(name)
    if body.compress:
        compress_result = compress_session(name)
    try:
        resume_session(name, source="web")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    _reset_agent()
    return {
        "ok": True,
        "session": current_session_name(),
        "thread_id": cfg.THREAD_ID,
        "session_ready": True,
        "consolidate": consolidate_result,
        "compress": compress_result,
        "needs_compress": session_needs_compress(name),
    }


@app.get("/api/session/log")
def api_session_log(name: str | None = Query(None)) -> dict:
    _ensure_boot()
    if name:
        try:
            events = get_session_events(name)
        except FileNotFoundError:
            raise HTTPException(404, f"会话不存在: {name}") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"name": name, "events": events, "format": "jsonl"}
    _require_session()
    text = current_session_log_text()
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return {"name": current_session_name(), "events": events, "raw": text, "format": "jsonl"}


@app.get("/api/session/subagents")
def api_session_subagents(name: str | None = Query(None)) -> dict:
    """父会话下的子代理列表（供标题下拉点击打开轨迹）。"""
    _ensure_boot()
    session = name or current_session_name()
    if not session:
        raise HTTPException(400, "缺少会话名")
    # 若传入的是 solver 路径，取其父会话
    if "/solver/" in session:
        session = session.split("/solver/", 1)[0]
    try:
        items = list_session_subagents(session)
    except FileNotFoundError:
        raise HTTPException(404, f"会话不存在: {session}") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"session": session, "subagents": items, "count": len(items)}


@app.get("/api/session/download")
def api_session_download(name: str | None = Query(None)):
    _ensure_boot()
    if name:
        try:
            events = get_session_events(name)
        except FileNotFoundError:
            raise HTTPException(404, f"会话不存在: {name}") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        body = "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n"
        fname = f"{name.replace('/', '_')}.jsonl"
    else:
        _require_session()
        body = current_session_log_text()
        fname = f"{current_session_name()}.jsonl"
    return Response(
        content=body.encode("utf-8"),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/tree")
def api_tree(max_depth: int = Query(4, ge=1, le=8)) -> dict:
    """工作区树：只列 OUTPUT_DIR 内的内容（绝不展示 skills / .memory）。"""
    _ensure_boot()
    out = cfg.OUTPUT_DIR.resolve()
    out.mkdir(parents=True, exist_ok=True)
    out_name = out.name or ".output"

    children = []
    try:
        entries = sorted(out.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        entries = []
    for child in entries:
        if not _tree_name_allowed(child.name):
            continue
        children.append(
            _tree_node(child, f"{out_name}/{child.name}", max_depth=max_depth, depth=0)
        )
    return {
        "roots": children,
        "output_dir": str(cfg.OUTPUT_DIR),
        "root_name": out_name,
    }


@app.get("/api/file")
def api_file(path: str = Query(..., min_length=1)) -> dict:
    _ensure_boot()
    fp = _resolve_visible(path)
    if not fp.exists():
        raise HTTPException(404, "文件不存在")
    if fp.is_dir():
        raise HTTPException(400, "路径是目录")
    try:
        text = fp.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {
            "path": path,
            "name": fp.name,
            "binary": True,
            "content": f"（二进制文件，{fp.stat().st_size} 字节，不可预览）",
            "language": "",
        }
    truncated = False
    if len(text) > 200_000:
        text = text[:200_000] + "\n\n…（已截断）"
        truncated = True
    suffix = fp.suffix.lower()
    language = {
        ".md": "markdown",
        ".py": "python",
        ".json": "json",
        ".jsonl": "jsonl",
        ".sql": "sql",
        ".sh": "bash",
        ".js": "javascript",
        ".ts": "typescript",
        ".css": "css",
        ".html": "html",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".toml": "toml",
        ".txt": "text",
    }.get(suffix, "text")
    return {
        "path": path,
        "name": fp.name,
        "binary": False,
        "content": text,
        "language": language,
        "truncated": truncated,
    }


def _msg_text(msg) -> str:
    c = getattr(msg, "content", "")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for p in c:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text", ""))
            elif isinstance(p, str):
                parts.append(p)
        return "\n".join(parts)
    return str(c or "")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _emit_update(update: dict) -> Iterator[bytes]:
    if not isinstance(update, dict):
        return
    for node_name, payload in update.items():
        if not isinstance(payload, dict):
            continue
        messages = payload.get("messages") or []
        if not isinstance(messages, list):
            messages = [messages]
        for msg in messages:
            if isinstance(msg, ToolMessage):
                yield _sse(
                    "tool",
                    {
                        "name": getattr(msg, "name", "") or "tool",
                        "content": _msg_text(msg)[:8000],
                        "node": node_name,
                    },
                ).encode("utf-8")
            elif isinstance(msg, AIMessage):
                tcs = getattr(msg, "tool_calls", None) or []
                if tcs:
                    yield _sse(
                        "tool_call",
                        {
                            "calls": [
                                {
                                    "name": tc.get("name")
                                    if isinstance(tc, dict)
                                    else getattr(tc, "name", ""),
                                    "args": tc.get("args")
                                    if isinstance(tc, dict)
                                    else getattr(tc, "args", {}),
                                }
                                for tc in tcs
                            ],
                            "node": node_name,
                        },
                    ).encode("utf-8")
                text = _msg_text(msg).strip()
                if text and not tcs:
                    yield _sse(
                        "assistant",
                        {"content": text, "node": node_name},
                    ).encode("utf-8")
                elif text and tcs:
                    yield _sse(
                        "assistant_partial",
                        {"content": text, "node": node_name},
                    ).encode("utf-8")


def _chat_stream(message: str, thread_id: str) -> Iterator[bytes]:
    agent = _get_agent()
    config = {"configurable": {"thread_id": thread_id}}
    ev_q: queue.Queue = queue.Queue()
    local_req_ids: set[str] = set()

    def approver(tool_name: str, args: dict, reason: str) -> bool:
        req_id = uuid.uuid4().hex
        done = threading.Event()
        holder: dict[str, Any] = {"event": done, "allow": False}
        with _pending_lock:
            _pending_approvals[req_id] = holder
            local_req_ids.add(req_id)
        ev_q.put(
            (
                "permission",
                {
                    "request_id": req_id,
                    "tool": tool_name,
                    "args": args,
                    "reason": reason,
                    "command": (args or {}).get("command", ""),
                    "timeout_sec": PERMISSION_TIMEOUT_SEC,
                },
            )
        )
        ok = done.wait(timeout=PERMISSION_TIMEOUT_SEC)
        with _pending_lock:
            _pending_approvals.pop(req_id, None)
            local_req_ids.discard(req_id)
        if not ok:
            return False
        return bool(holder.get("allow"))

    def worker() -> None:
        token = bind_approver(approver)
        try:
            for update in agent.stream(
                {"messages": [HumanMessage(content=message)]},
                config=config,
                stream_mode="updates",
            ):
                ev_q.put(("update", update))
            ev_q.put(("done", None))
        except Exception as e:
            ev_q.put(("error", e))
        finally:
            reset_approver(token)
            with _pending_lock:
                leftovers = [rid for rid in list(local_req_ids) if rid in _pending_approvals]
                for rid in leftovers:
                    h = _pending_approvals.pop(rid, None)
                    if h:
                        h["allow"] = False
                        h["event"].set()
                local_req_ids.clear()

    yield _sse(
        "status",
        {"message": "开始处理…", "thread_id": thread_id, "session": current_session_name()},
    ).encode("utf-8")
    threading.Thread(target=worker, name=f"chat-{thread_id}", daemon=True).start()

    while True:
        kind, payload = ev_q.get()
        if kind == "permission":
            yield _sse("permission", payload).encode("utf-8")
            yield _sse(
                "status",
                {"message": "等待权限确认…", "request_id": payload.get("request_id")},
            ).encode("utf-8")
        elif kind == "update":
            yield from _emit_update(payload if isinstance(payload, dict) else {})
        elif kind == "done":
            yield _sse("done", {"ok": True}).encode("utf-8")
            break
        elif kind == "error":
            yield _sse("error", {"message": str(payload)}).encode("utf-8")
            break


@app.post("/api/permission")
def api_permission(body: PermissionDecision) -> dict:
    with _pending_lock:
        holder = _pending_approvals.get(body.request_id)
        if holder is None:
            raise HTTPException(404, "无此权限请求或已过期")
        holder["allow"] = bool(body.allow)
        holder["event"].set()
    return {"ok": True, "allow": bool(body.allow), "request_id": body.request_id}


@app.post("/api/chat")
def api_chat(body: ChatRequest) -> StreamingResponse:
    _ensure_boot()
    _require_session()
    thread_id = (body.thread_id or "").strip() or cfg.THREAD_ID
    return StreamingResponse(
        _chat_stream(body.message.strip(), thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/")
def index() -> FileResponse:
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(500, "缺少 serve/web/index.html")
    return FileResponse(index_path)


if WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Claude-code-mini Web")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--output-dir", "-o", default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.output_dir:
        set_output_dir(args.output_dir)
    _ensure_boot()
    import uvicorn

    print("Claude-code-mini Web（Planner + Solver）")
    print(f"  http://{args.host}:{args.port}")
    print(f"  OUTPUT_DIR: {cfg.OUTPUT_DIR}")
    print("  会话：浏览器内选择「新建」或打开 .memory/session_*/")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
