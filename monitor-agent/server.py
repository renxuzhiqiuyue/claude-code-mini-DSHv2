"""Session / MEMORY 监控服务：默认根目录为 claude-code-mini/.memory，端口 40000。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DEFAULT_MEMORY_ROOT = (APP_DIR.parent / ".memory").resolve()
MEMORY_ROOT = Path(os.getenv("MEMORY_ROOT", str(DEFAULT_MEMORY_ROOT))).resolve()

app = FastAPI(title="monitor-agent", description="浏览 .memory 会话 JSON")


def _safe_resolve(rel: str) -> Path:
    """相对 MEMORY_ROOT 的路径，禁止逃逸。"""
    raw = (rel or "").strip().lstrip("/")
    if not raw or raw in (".",):
        return MEMORY_ROOT
    target = (MEMORY_ROOT / raw).resolve()
    try:
        target.relative_to(MEMORY_ROOT)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="路径逃逸") from e
    return target


def _build_tree(path: Path, rel_prefix: str = "") -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    try:
        children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return nodes
    for child in children:
        # 隐藏点文件中的 consolidate_state 仍展示；其它以 . 开头的可显示
        name = child.name
        rel = f"{rel_prefix}/{name}" if rel_prefix else name
        if child.is_dir():
            nodes.append(
                {
                    "name": name,
                    "path": rel.replace("\\", "/"),
                    "type": "dir",
                    "children": _build_tree(child, rel.replace("\\", "/")),
                }
            )
        else:
            nodes.append(
                {
                    "name": name,
                    "path": rel.replace("\\", "/"),
                    "type": "file",
                    "ext": child.suffix.lower(),
                }
            )
    return nodes


def _normalize_message(item: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return {
            "index": index,
            "role": "Unknown",
            "summary": str(item)[:200],
            "content": str(item),
            "details": {},
        }

    if "HumanMessage" in item:
        content = item["HumanMessage"]
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        return {
            "index": index,
            "role": "HumanMessage",
            "summary": (text or "").strip().replace("\n", " ")[:120] or "（空）",
            "content": text if isinstance(text, str) else str(text),
            "details": {},
        }

    if "AIMessage" in item:
        raw = item["AIMessage"]
        details: dict[str, Any] = {}
        if isinstance(raw, dict):
            content = raw.get("content") or ""
            tcs = raw.get("tool_calls") or []
            details["tool_calls"] = tcs
            if not content and tcs:
                names = [tc.get("name", "?") for tc in tcs if isinstance(tc, dict)]
                summary = f"tool_calls: {', '.join(names)}" if names else "（仅 tool_calls）"
            else:
                summary = (str(content).strip().replace("\n", " ")[:120] or "（空）")
            return {
                "index": index,
                "role": "AIMessage",
                "summary": summary,
                "content": content if isinstance(content, str) else str(content),
                "details": details,
            }
        text = str(raw)
        return {
            "index": index,
            "role": "AIMessage",
            "summary": text.strip().replace("\n", " ")[:120] or "（空）",
            "content": text,
            "details": {},
        }

    if "ToolMessage" in item:
        raw = item["ToolMessage"]
        if isinstance(raw, dict):
            content = raw.get("content") or ""
            name = raw.get("name") or ""
            tid = raw.get("tool_call_id") or ""
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            summary = f"{name}: " + (text.strip().replace("\n", " ")[:100] if text else "（空）")
            return {
                "index": index,
                "role": "ToolMessage",
                "summary": summary,
                "content": text,
                "details": {"name": name, "tool_call_id": tid},
            }
        text = str(raw)
        return {
            "index": index,
            "role": "ToolMessage",
            "summary": text.strip().replace("\n", " ")[:120] or "（空）",
            "content": text,
            "details": {},
        }

    # 其它键：整段展示
    role = next(iter(item.keys()), "Unknown")
    payload = item.get(role, item)
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    return {
        "index": index,
        "role": str(role),
        "summary": str(text).strip().replace("\n", " ")[:120] or "（空）",
        "content": text if isinstance(text, str) else str(text),
        "details": item if isinstance(item, dict) else {},
    }


def _parse_session_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败: {e}") from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    meta: dict[str, Any] = {}
    messages_raw: list = []

    if isinstance(data, dict):
        meta = {
            k: v
            for k, v in data.items()
            if k != "messages"
        }
        messages_raw = data.get("messages") or []
    elif isinstance(data, list):
        messages_raw = data
    else:
        raise HTTPException(status_code=400, detail="不支持的 JSON 结构")

    messages = []
    for i, item in enumerate(messages_raw):
        norm = _normalize_message(item, i)
        if norm:
            messages.append(norm)

    return {
        "path": str(path.relative_to(MEMORY_ROOT)).replace("\\", "/"),
        "meta": meta,
        "messages": messages,
        "message_count": len(messages),
        "raw_kind": "session",
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "memory_root": str(MEMORY_ROOT),
        "exists": MEMORY_ROOT.is_dir(),
    }


@app.get("/api/tree")
def tree() -> dict[str, Any]:
    if not MEMORY_ROOT.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在: {MEMORY_ROOT}")
    return {
        "root": str(MEMORY_ROOT),
        "root_name": MEMORY_ROOT.name,
        "children": _build_tree(MEMORY_ROOT),
    }


@app.get("/api/file")
def read_file(path: str = Query(..., description="相对 MEMORY_ROOT 的路径")) -> dict[str, Any]:
    target = _safe_resolve(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="请选择文件而非目录")

    rel = str(target.relative_to(MEMORY_ROOT)).replace("\\", "/")
    if target.suffix.lower() == ".json":
        parsed = _parse_session_file(target)
        # 非 session 结构（如 consolidate_state）：仍返回可读 JSON
        if parsed["message_count"] == 0 and not parsed.get("meta"):
            try:
                raw = json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                raw = None
            if raw is not None and not (
                isinstance(raw, dict) and "messages" in raw
            ) and not isinstance(raw, list):
                return {
                    "path": rel,
                    "kind": "json",
                    "meta": {},
                    "messages": [],
                    "message_count": 0,
                    "raw": raw,
                    "text": json.dumps(raw, ensure_ascii=False, indent=2),
                }
        parsed["kind"] = "session"
        return parsed

    # Markdown / 其它文本
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="非文本文件") from None
    return {
        "path": rel,
        "kind": "text",
        "meta": {},
        "messages": [],
        "message_count": 0,
        "text": text,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main() -> None:
    import uvicorn

    host = os.getenv("MONITOR_HOST", "0.0.0.0")
    port = int(os.getenv("MONITOR_PORT", "40000"))
    print(f"monitor-agent  MEMORY_ROOT={MEMORY_ROOT}")
    print(f"  http://127.0.0.1:{port}/")
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
