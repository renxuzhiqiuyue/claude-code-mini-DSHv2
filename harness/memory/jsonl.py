"""session.jsonl 读写、事件与消息互转。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from harness.memory import paths, runtime
from harness.memory.constants import DIALOGUE_EVENT_TYPES, SESSION_COMPRESS_MARKER, SESSION_JSONL
from harness.memory.files import ensure_memory_files


def now_iso() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def mono_iso_for(path: Path) -> str:
    """当前时间；若与上次写入同毫秒或回退，则 +1ms，避免轨迹条宽全变成同一值。"""
    key = str(path.resolve())
    ms = int(datetime.now().timestamp() * 1000)
    prev = runtime.last_event_ts_ms.get(key)
    if prev is not None and ms <= prev:
        ms = prev + 1
    runtime.last_event_ts_ms[key] = ms
    return datetime.fromtimestamp(ms / 1000.0).isoformat(timespec="milliseconds")


def note_event_ts(path: Path, ts: str | None) -> None:
    if not ts:
        return
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        ms = int(dt.timestamp() * 1000)
    except Exception:
        return
    key = str(path.resolve())
    prev = runtime.last_event_ts_ms.get(key, 0)
    if ms > prev:
        runtime.last_event_ts_ms[key] = ms


def is_session_dir(path: Path) -> bool:
    return path.is_dir() and path.name.startswith("session_") and (path / SESSION_JSONL).is_file()


def iter_session_dirs() -> list[Path]:
    """新→旧。"""
    ensure_memory_files()
    dirs = [p for p in paths.MEMORY_DIR.iterdir() if is_session_dir(p)]
    return sorted(dirs, key=lambda p: p.name, reverse=True)


def read_jsonl_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("type"):
            events.append(obj)
    return events


def append_jsonl_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    if payload.get("ts"):
        note_event_ts(path, str(payload["ts"]))
    else:
        payload["ts"] = mono_iso_for(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_jsonl_meta(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"type": "session/meta", "ts": now_iso(), **meta}
    path.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")


def rewrite_session_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for ev in events:
        payload = dict(ev)
        if not payload.get("ts"):
            payload["ts"] = mono_iso_for(path)
        lines.append(json.dumps(payload, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def meta_from_events(events: list[dict]) -> dict:
    meta: dict = {}
    for ev in events:
        if ev.get("type") == "session/meta":
            for k, v in ev.items():
                if k in ("type", "ts"):
                    continue
                meta[k] = v
    return meta


def events_to_messages(events: list[dict]) -> list[dict]:
    messages: list[dict] = []
    for ev in events:
        t = ev.get("type")
        if t == "user/message":
            messages.append({"HumanMessage": ev.get("text") or ""})
        elif t == "assistant/message":
            text = ev.get("text") or ""
            tcs = ev.get("tool_calls") or []
            if tcs:
                messages.append({"AIMessage": {"content": text, "tool_calls": tcs}})
            else:
                messages.append({"AIMessage": text})
        elif t == "tool/result":
            messages.append(
                {
                    "ToolMessage": {
                        "content": ev.get("content") or "",
                        "tool_call_id": ev.get("tool_call_id") or "",
                        "name": ev.get("name") or "",
                    }
                }
            )
    return messages


def load_session_view(session_dir: Path) -> dict:
    path = session_dir / SESSION_JSONL if session_dir.is_dir() else session_dir
    events = read_jsonl_events(path)
    meta = meta_from_events(events)
    return {
        "source": meta.get("source", ""),
        "started_at": meta.get("started_at", ""),
        "thread_id": meta.get("thread_id", "") or session_dir.name,
        "id": meta.get("id") or session_dir.name,
        "messages": events_to_messages(events),
        "events": events,
        "dir": session_dir.name if session_dir.is_dir() else session_dir.parent.name,
    }


def content_text(msg) -> str:
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


def msg_to_events(msg) -> list[dict]:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    if isinstance(msg, HumanMessage):
        text = content_text(msg)
        if text.startswith("<reminder>") or text.startswith("<ai-history-summary>"):
            return []
        return [{"type": "user/message", "text": text}]
    if isinstance(msg, AIMessage):
        text = content_text(msg)
        tcs = getattr(msg, "tool_calls", None) or []
        tool_calls = [
            {
                "name": tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", ""),
                "args": tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {}),
                "id": tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", ""),
            }
            for tc in tcs
        ]
        events: list[dict] = [
            {
                "type": "assistant/message",
                "text": text,
                **({"tool_calls": tool_calls} if tool_calls else {}),
            }
        ]
        for tc in tool_calls:
            events.append(
                {
                    "type": "tool/call",
                    "tool_call_id": tc.get("id") or "",
                    "name": tc.get("name") or "",
                    "args": tc.get("args") or {},
                }
            )
        return events
    if isinstance(msg, ToolMessage):
        return [
            {
                "type": "tool/result",
                "content": content_text(msg),
                "tool_call_id": getattr(msg, "tool_call_id", "") or "",
                "name": getattr(msg, "name", "") or "",
            }
        ]
    return []


def event_fingerprint(ev: dict) -> str:
    payload = {k: v for k, v in ev.items() if k != "ts"}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def session_has_dialogue(session_dir: Path) -> bool:
    view = load_session_view(session_dir)
    for item in view.get("messages") or []:
        if isinstance(item, dict) and "HumanMessage" in item:
            text = item.get("HumanMessage") or ""
            if isinstance(text, str) and text.strip():
                return True
    return False


def session_as_dialogue_text(session_dir: Path) -> str:
    view = load_session_view(session_dir)
    lines = [
        f"----- {session_dir.name} -----",
        f"source={view.get('source')} started={view.get('started_at')}",
    ]
    for item in view.get("messages") or []:
        if not isinstance(item, dict):
            continue
        if "HumanMessage" in item:
            lines.append(f"用户：{item['HumanMessage']}")
        elif "AIMessage" in item:
            v = item["AIMessage"]
            if isinstance(v, dict):
                lines.append(f"助手：{v.get('content', '')}")
                if v.get("tool_calls"):
                    lines.append(f"  tool_calls：{json.dumps(v['tool_calls'], ensure_ascii=False)}")
            else:
                lines.append(f"助手：{v}")
        elif "ToolMessage" in item:
            v = item["ToolMessage"]
            if isinstance(v, dict):
                lines.append(f"工具({v.get('name','')})：{str(v.get('content', ''))[:2000]}")
            else:
                lines.append(f"工具：{v}")
    return "\n".join(lines)


def count_dialogue_events(events: list[dict]) -> int:
    return sum(1 for e in events if isinstance(e, dict) and e.get("type") in DIALOGUE_EVENT_TYPES)


def session_is_compressed_only(events: list[dict]) -> bool:
    dialogue = [e for e in events if isinstance(e, dict) and e.get("type") in DIALOGUE_EVENT_TYPES]
    if len(dialogue) != 2:
        return False
    user_ev, ai_ev = dialogue
    return (
        user_ev.get("type") == "user/message"
        and str(user_ev.get("text") or "").startswith(SESSION_COMPRESS_MARKER)
        and ai_ev.get("type") == "assistant/message"
        and bool(str(ai_ev.get("text") or "").strip())
    )


def initial_session_meta(events: list[dict]) -> dict:
    for ev in events:
        if ev.get("type") == "session/meta" and not ev.get("resumed"):
            meta = {k: v for k, v in ev.items() if k not in ("type", "ts", "resumed")}
            if meta:
                return meta
    return {}


def strip_session_name(session_name: str) -> str:
    name = (session_name or "").strip().rstrip("/")
    if name.startswith(".memory/"):
        name = name.split("/", 1)[1]
    return name
