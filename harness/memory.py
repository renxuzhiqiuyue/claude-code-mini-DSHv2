"""分层记忆（程序确定性时机读写，不经 OUTPUT_DIR）。

会话布局（每会话一个文件夹）：
  .memory/
    MEMORY.md
    session_<slug>/
      session.jsonl          # Planner 轨迹
      solver/
        session_<slug>.jsonl # 每次 Solver 子轨迹

无旧版 .json / 平铺 .jsonl 兼容。
"""

from __future__ import annotations

import json
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from harness.config import MEMORY_DIR

MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
STATE_FILE = MEMORY_DIR / ".consolidate_state.json"
SESSION_JSONL = "session.jsonl"
SHORT_TERM_MAX = 3
SESSION_COMPRESS_USER_TEXT = "【历史会话压缩】请将此前完整对话总结为简明摘要，便于后续继续本话题。"
SESSION_COMPRESS_MARKER = "【历史会话压缩】"

_short_term: deque[dict] = deque(maxlen=SHORT_TERM_MAX)
_current_session_dir: Path | None = None
_current_session: Path | None = None  # .../session.jsonl
_session_started_at: str = ""
_session_meta: dict = {}
_solver_session: Path | None = None
_solver_session_meta: dict = {}

MEMORY_TEMPLATE = """---
name: user-memory
description: 用户分层记忆。默认仅加载「记忆种类」与「用户画像与偏好」；短期/长期请用 load_memory 按需加载。
---

# 用户记忆

本文件由 Harness 在**每次启动**时视「是否有新对话」用大模型增量更新；非工具沙箱产物。

## 记忆种类与目的

| 种类 | 层级 | 目的 | 默认注入 | 按需加载 |
|------|------|------|----------|----------|
| 短期记忆（工作记忆） | L1 | 最近约三次询问摘要 | 否 | `load_memory("short")` |
| 长期·语义记忆 | L2 | 稳定事实与概念 | 否 | `load_memory("long")` |
| 长期·情节记忆 | L2 | 过往会话/事件 | 否 | `load_memory("long")` |
| 长期·程序记忆 | L2 | 「怎么做」的习惯与步骤 | 否 | `load_memory("long")` |
| 用户画像与偏好 | L3 | 身份、沟通与编码偏好 | 是 | （已在 system） |

## 用户画像与偏好

### 画像
- （暂无）

### 偏好
- （暂无）

## 短期记忆

（最近约三次询问摘要；启动 Consolidation 时由模型更新）

## 长期记忆

### 语义记忆
- （暂无）

### 情节记忆
- （暂无）

### 程序记忆
- （暂无）
"""


def ensure_memory_files() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text(MEMORY_TEMPLATE, encoding="utf-8")


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    meta: dict = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, parts[2].strip()


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"consolidated": []}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"consolidated": []}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


# 每个 jsonl 文件最近写入的毫秒时间戳，保证同文件内 ts 单调递增
_last_event_ts_ms: dict[str, int] = {}


def _mono_iso_for(path: Path) -> str:
    """当前时间；若与上次写入同毫秒或回退，则 +1ms，避免轨迹条宽全变成同一值。"""
    key = str(path.resolve())
    ms = int(datetime.now().timestamp() * 1000)
    prev = _last_event_ts_ms.get(key)
    if prev is not None and ms <= prev:
        ms = prev + 1
    _last_event_ts_ms[key] = ms
    return datetime.fromtimestamp(ms / 1000.0).isoformat(timespec="milliseconds")


def _note_event_ts(path: Path, ts: str | None) -> None:
    if not ts:
        return
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        ms = int(dt.timestamp() * 1000)
    except Exception:
        return
    key = str(path.resolve())
    prev = _last_event_ts_ms.get(key, 0)
    if ms > prev:
        _last_event_ts_ms[key] = ms


def _is_session_dir(path: Path) -> bool:
    return path.is_dir() and path.name.startswith("session_") and (path / SESSION_JSONL).is_file()


def iter_session_dirs() -> list[Path]:
    """新→旧。"""
    ensure_memory_files()
    dirs = [p for p in MEMORY_DIR.iterdir() if _is_session_dir(p)]
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
        _note_event_ts(path, str(payload["ts"]))
    else:
        payload["ts"] = _mono_iso_for(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_jsonl_meta(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"type": "session/meta", "ts": _now_iso(), **meta}
    path.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")


def _meta_from_events(events: list[dict]) -> dict:
    meta: dict = {}
    for ev in events:
        if ev.get("type") == "session/meta":
            for k, v in ev.items():
                if k in ("type", "ts"):
                    continue
                meta[k] = v
    return meta


def _events_to_messages(events: list[dict]) -> list[dict]:
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
    meta = _meta_from_events(events)
    return {
        "source": meta.get("source", ""),
        "started_at": meta.get("started_at", ""),
        "thread_id": meta.get("thread_id", "") or session_dir.name,
        "id": meta.get("id") or session_dir.name,
        "messages": _events_to_messages(events),
        "events": events,
        "dir": session_dir.name if session_dir.is_dir() else session_dir.parent.name,
    }


def _content_text(msg) -> str:
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


def _msg_to_events(msg) -> list[dict]:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    if isinstance(msg, HumanMessage):
        text = _content_text(msg)
        if text.startswith("<reminder>") or text.startswith("<ai-history-summary>"):
            return []
        return [{"type": "user/message", "text": text}]
    if isinstance(msg, AIMessage):
        text = _content_text(msg)
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
                "content": _content_text(msg),
                "tool_call_id": getattr(msg, "tool_call_id", "") or "",
                "name": getattr(msg, "name", "") or "",
            }
        ]
    return []


def _event_fingerprint(ev: dict) -> str:
    payload = {k: v for k, v in ev.items() if k != "ts"}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _session_has_dialogue(session_dir: Path) -> bool:
    view = load_session_view(session_dir)
    for item in view.get("messages") or []:
        if isinstance(item, dict) and "HumanMessage" in item:
            text = item.get("HumanMessage") or ""
            if isinstance(text, str) and text.strip():
                return True
    return False


def _mark_consolidated(session_name: str, *, updated: bool) -> None:
    state = _load_state()
    done = set(state.get("consolidated") or [])
    done.add(session_name)
    state["consolidated"] = sorted(done)
    if updated:
        state["last_update"] = datetime.now().isoformat(timespec="seconds")
    _save_state(state)


def _session_as_dialogue_text(session_dir: Path) -> str:
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


def consolidate_session(session_name: str) -> dict:
    """将指定会话目录总结进 MEMORY.md。

    Returns:
        {"ok": bool, "updated": bool, "message": str, "session": str}
    """
    ensure_memory_files()
    name = (session_name or "").strip().rstrip("/")
    if name.startswith(".memory/"):
        name = name.split("/", 1)[1]
    if "/" in name or ".." in name or not name.startswith("session_"):
        return {"ok": False, "updated": False, "message": f"非法会话名: {session_name}", "session": name}

    session_dir = MEMORY_DIR / name
    if not _is_session_dir(session_dir):
        return {"ok": False, "updated": False, "message": f"会话不存在: {name}", "session": name}

    if not _session_has_dialogue(session_dir):
        _mark_consolidated(name, updated=False)
        return {
            "ok": True,
            "updated": False,
            "message": "该会话无可总结的对话",
            "session": name,
        }

    dialogue = _session_as_dialogue_text(session_dir)
    memory = MEMORY_FILE.read_text(encoding="utf-8")
    print(f"  \033[36m[memory] 总结会话 {name} → MEMORY.md …\033[0m")
    try:
        from agents.agent import run_memory_consolidation

        text = run_memory_consolidation(memory=memory, dialogue=dialogue[:80000])
    except Exception as e:
        msg = f"模型更新失败: {e}"
        print(f"  \033[31m[memory] {msg}\033[0m")
        return {"ok": False, "updated": False, "message": msg, "session": name}

    if not text or "[[NO_UPDATE]]" in text.splitlines()[0] or text.strip() == "[[NO_UPDATE]]":
        _mark_consolidated(name, updated=False)
        print("  \033[90m[memory] 模型判断无需补充，MEMORY.md 未改\033[0m")
        return {
            "ok": True,
            "updated": False,
            "message": "模型判断无需补充，MEMORY.md 未改",
            "session": name,
        }

    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\n", "", text)
        text = re.sub(r"\n```$", "", text)

    if not (text.lstrip().startswith("#") or text.lstrip().startswith("---")):
        print("  \033[33m[memory] 模型输出格式异常，放弃写入\033[0m")
        return {
            "ok": False,
            "updated": False,
            "message": "模型输出格式异常，未写入 MEMORY.md",
            "session": name,
        }

    MEMORY_FILE.write_text(text.rstrip() + "\n", encoding="utf-8")
    _mark_consolidated(name, updated=True)
    print("  \033[32m[memory] MEMORY.md 已由模型增量更新\033[0m")
    return {
        "ok": True,
        "updated": True,
        "message": "已将会话要点写入 MEMORY.md",
        "session": name,
    }


_DIALOGUE_EVENT_TYPES = frozenset(
    {"user/message", "assistant/message", "tool/call", "tool/result"}
)


def _count_dialogue_events(events: list[dict]) -> int:
    return sum(1 for e in events if isinstance(e, dict) and e.get("type") in _DIALOGUE_EVENT_TYPES)


def _session_is_compressed_only(events: list[dict]) -> bool:
    dialogue = [e for e in events if isinstance(e, dict) and e.get("type") in _DIALOGUE_EVENT_TYPES]
    if len(dialogue) != 2:
        return False
    user_ev, ai_ev = dialogue
    return (
        user_ev.get("type") == "user/message"
        and str(user_ev.get("text") or "").startswith(SESSION_COMPRESS_MARKER)
        and ai_ev.get("type") == "assistant/message"
        and bool(str(ai_ev.get("text") or "").strip())
    )


def session_needs_compress(session_name: str) -> bool:
    """是否仍有可压缩的历史对话（已压缩为摘要对则不再提示）。"""
    name = (session_name or "").strip().rstrip("/")
    if name.startswith(".memory/"):
        name = name.split("/", 1)[1]
    session_dir = MEMORY_DIR / name
    if not _is_session_dir(session_dir):
        return False
    events = read_jsonl_events(session_dir / SESSION_JSONL)
    if not _session_has_dialogue(session_dir):
        return False
    if _session_is_compressed_only(events):
        return False
    return _count_dialogue_events(events) > 0


def _initial_session_meta(events: list[dict]) -> dict:
    for ev in events:
        if ev.get("type") == "session/meta" and not ev.get("resumed"):
            meta = {k: v for k, v in ev.items() if k not in ("type", "ts", "resumed")}
            if meta:
                return meta
    return {}


def _rewrite_session_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for ev in events:
        payload = dict(ev)
        if not payload.get("ts"):
            payload["ts"] = _mono_iso_for(path)
        lines.append(json.dumps(payload, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compress_session(session_name: str) -> dict:
    """将历史会话压成「用户压缩请求 + 助手摘要」两条消息，重写 session.jsonl。

    Returns:
        {"ok": bool, "compressed": bool, "message": str, "session": str, "summary": str}
    """
    ensure_memory_files()
    name = (session_name or "").strip().rstrip("/")
    if name.startswith(".memory/"):
        name = name.split("/", 1)[1]
    if "/" in name or ".." in name or not name.startswith("session_"):
        return {
            "ok": False,
            "compressed": False,
            "message": f"非法会话名: {session_name}",
            "session": name,
            "summary": "",
        }

    session_dir = MEMORY_DIR / name
    if not _is_session_dir(session_dir):
        return {
            "ok": False,
            "compressed": False,
            "message": f"会话不存在: {name}",
            "session": name,
            "summary": "",
        }

    jsonl = session_dir / SESSION_JSONL
    events = read_jsonl_events(jsonl)
    if not _session_has_dialogue(session_dir):
        return {
            "ok": True,
            "compressed": False,
            "message": "该会话无可压缩的对话",
            "session": name,
            "summary": "",
        }
    if _session_is_compressed_only(events):
        return {
            "ok": True,
            "compressed": False,
            "message": "会话已是压缩摘要，无需重复",
            "session": name,
            "summary": "",
        }

    dialogue = _session_as_dialogue_text(session_dir)
    print(f"  \033[36m[memory] 压缩会话历史 {name} …\033[0m")
    try:
        from agents.agent import run_session_compression

        summary = run_session_compression(dialogue=dialogue[:80000])
    except Exception as e:
        msg = f"会话压缩失败: {e}"
        print(f"  \033[31m[memory] {msg}\033[0m")
        return {
            "ok": False,
            "compressed": False,
            "message": msg,
            "session": name,
            "summary": "",
        }

    if not summary.strip():
        return {
            "ok": False,
            "compressed": False,
            "message": "模型未返回有效摘要",
            "session": name,
            "summary": "",
        }

    meta = _initial_session_meta(events) or {
        "source": "web",
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "thread_id": session_dir.name,
        "id": session_dir.name,
    }
    meta = dict(meta)
    meta["history_compressed"] = True
    meta["compressed_at"] = datetime.now().isoformat(timespec="seconds")

    new_events: list[dict] = [
        {"type": "session/meta", **meta},
        {"type": "user/message", "text": SESSION_COMPRESS_USER_TEXT},
        {"type": "assistant/message", "text": summary.strip()},
    ]
    _rewrite_session_jsonl(jsonl, new_events)

    global _current_session, _current_session_dir, _short_term
    if _current_session_dir and _current_session_dir.name == name:
        _current_session = jsonl
        view = load_session_view(session_dir)
        _rebuild_short_term_from_view(view)

    print(f"  \033[32m[memory] 会话 {name} 历史已压缩为摘要\033[0m")
    return {
        "ok": True,
        "compressed": True,
        "message": "历史会话已压缩为摘要",
        "session": name,
        "summary": summary.strip()[:500],
    }


def is_session_consolidated(session_name: str) -> bool:
    state = _load_state()
    return session_name in set(state.get("consolidated") or [])


def _set_thread_id(thread_id: str) -> None:
    import harness.config as cfg

    cfg.THREAD_ID = (thread_id or "").strip() or cfg.THREAD_ID


def _rebuild_short_term_from_view(view: dict) -> None:
    _short_term.clear()
    for entry in view.get("messages") or []:
        if not isinstance(entry, dict):
            continue
        if "HumanMessage" in entry:
            q = entry["HumanMessage"]
            if isinstance(q, str) and q.strip():
                _short_term.append({"user": q.strip()[:500], "summary": ""})
        elif "AIMessage" in entry and _short_term:
            v = entry["AIMessage"]
            text = v.get("content", "") if isinstance(v, dict) else str(v)
            _short_term[-1]["summary"] = (text or "")[:800]


def _activate_session_dir(session_dir: Path, *, source: str, resume: bool) -> Path:
    global _current_session_dir, _current_session, _session_started_at, _session_meta, _short_term
    jsonl = session_dir / SESSION_JSONL
    view = load_session_view(session_dir)
    thread_id = str(view.get("thread_id") or session_dir.name)
    _set_thread_id(thread_id)
    _current_session_dir = session_dir
    _current_session = jsonl
    _session_started_at = str(view.get("started_at") or "")
    _session_meta = {
        "source": view.get("source") or source,
        "started_at": _session_started_at,
        "thread_id": thread_id,
        "id": session_dir.name,
    }
    if resume:
        append_jsonl_event(
            jsonl,
            {
                "type": "session/meta",
                "source": _session_meta["source"],
                "started_at": _session_started_at,
                "thread_id": thread_id,
                "id": session_dir.name,
                "resumed": True,
            },
        )
        _rebuild_short_term_from_view(view)
    else:
        _short_term.clear()
    return jsonl


def create_new_session(source: str = "cli") -> Path:
    """新建会话目录；thread_id = 目录名（进程内）。"""
    global _current_session_dir, _current_session, _session_started_at, _session_meta, _short_term

    ensure_memory_files()
    _short_term.clear()

    ts = datetime.now()
    _session_started_at = ts.strftime("%Y-%m-%d %H:%M:%S")
    slug = ts.strftime("%Y%m%d_%H%M%S_%f")
    session_dir = MEMORY_DIR / f"session_{slug}"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "solver").mkdir(exist_ok=True)
    jsonl = session_dir / SESSION_JSONL
    thread_id = session_dir.name
    _set_thread_id(thread_id)

    _session_meta = {
        "source": source,
        "started_at": _session_started_at,
        "thread_id": thread_id,
        "id": session_dir.name,
    }
    _write_jsonl_meta(jsonl, _session_meta)
    _current_session_dir = session_dir
    _current_session = jsonl
    print(f"  \033[90m[memory] 新会话: .memory/{session_dir.name}/\033[0m")
    return jsonl


def resume_session(name: str, *, source: str = "cli") -> Path:
    """打开已有会话目录。"""
    ensure_memory_files()
    name = (name or "").strip().rstrip("/")
    if name.startswith(".memory/"):
        name = name.split("/", 1)[1]
    if "/" in name or ".." in name or not name.startswith("session_"):
        raise ValueError(f"非法会话名: {name}")
    session_dir = MEMORY_DIR / name
    if not _is_session_dir(session_dir):
        raise FileNotFoundError(f"会话不存在: {name}")
    jsonl = _activate_session_dir(session_dir, source=source, resume=True)
    n = len(load_session_view(session_dir).get("messages") or [])
    print(f"  \033[90m[memory] 续聊: .memory/{session_dir.name}/（已有 {n} 条消息）\033[0m")
    return jsonl


def prompt_choose_session(*, source: str = "cli") -> Path:
    """交互：新建或选择已有会话。非 TTY 时默认新建。"""
    import sys

    sessions = iter_session_dirs()
    if not sys.stdin.isatty():
        print("  \033[33m[memory] 非交互环境，自动新建会话\033[0m")
        return create_new_session(source=source)

    print("\n选择会话：")
    print("  0) 新建会话")
    for i, d in enumerate(sessions[:30], 1):
        view = load_session_view(d)
        title = ""
        for m in view.get("messages") or []:
            if isinstance(m, dict) and "HumanMessage" in m:
                title = str(m["HumanMessage"] or "")[:48]
                break
        label = title or "(空)"
        print(f"  {i}) {d.name}  · {label}")
    if not sessions:
        print("  （尚无历史会话）")

    while True:
        try:
            raw = input("\033[36m请输入编号 [0]：\033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raw = "0"
        if raw == "":
            raw = "0"
        if not raw.isdigit():
            print("请输入数字编号")
            continue
        idx = int(raw)
        if idx == 0:
            return create_new_session(source=source)
        if 1 <= idx <= min(30, len(sessions)):
            chosen = sessions[idx - 1]
            do_compress = False
            if session_needs_compress(chosen.name):
                try:
                    ans = input(
                        f"\033[36m是否压缩「{chosen.name}」的历史对话为摘要？[y/N]：\033[0m"
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    ans = "n"
                do_compress = ans in ("y", "yes", "是")
            if _session_has_dialogue(chosen):
                try:
                    ans = input(
                        f"\033[36m是否将「{chosen.name}」的会话总结写入 MEMORY.md？[y/N]：\033[0m"
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    ans = "n"
                if ans in ("y", "yes", "是"):
                    consolidate_session(chosen.name)
            if do_compress:
                compress_session(chosen.name)
            return resume_session(chosen.name, source=source)
        print("编号超出范围")


def start_session(
    source: str = "cli",
    *,
    mode: str = "prompt",
    session_name: str | None = None,
) -> Path:
    """启动会话。

    mode:
      - prompt：交互选择（默认）
      - new：新建
      - resume：续聊 session_name（必填）
    """
    ensure_memory_files()
    m = (mode or "prompt").strip().lower()
    if m == "new":
        return create_new_session(source=source)
    if m == "resume":
        if not session_name:
            raise ValueError("resume 需要 session_name")
        return resume_session(session_name, source=source)
    return prompt_choose_session(source=source)


def session_started() -> bool:
    return _current_session is not None


def _note_short_term(ev: dict) -> None:
    if ev.get("type") == "user/message":
        q = ev.get("text") or ""
        if isinstance(q, str) and q.strip():
            _short_term.append({"user": q.strip()[:500], "summary": ""})
    elif ev.get("type") == "assistant/message" and _short_term:
        _short_term[-1]["summary"] = (ev.get("text") or "")[:800]


def sync_session_messages(messages: list, *, reason: str = "") -> None:
    global _current_session
    if _current_session is None:
        raise RuntimeError("尚未选择会话：请先 start_session / create_new_session / resume_session")

    tag = f" ({reason})" if reason else ""
    new_events: list[dict] = []
    for msg in messages:
        new_events.extend(_msg_to_events(msg))

    existing = read_jsonl_events(_current_session)
    seen = {_event_fingerprint(e) for e in existing}
    added = 0
    for ev in new_events:
        fp = _event_fingerprint(ev)
        if fp in seen:
            continue
        append_jsonl_event(_current_session, ev)
        seen.add(fp)
        added += 1
        _note_short_term(ev)
    if added:
        print(f"  \033[90m[memory] 会话已写入 +{added} 条{tag}\033[0m")


def append_parent_event(event: dict) -> None:
    if _current_session is None:
        return
    append_jsonl_event(_current_session, event)


def start_solver_session(*, parent_session: str | None = None) -> Path:
    global _solver_session, _solver_session_meta
    if _current_session_dir is None:
        raise RuntimeError("无父会话，无法启动 Solver")
    ensure_memory_files()
    ts = datetime.now()
    slug = ts.strftime("%Y%m%d_%H%M%S_%f")
    solver_dir = _current_session_dir / "solver"
    solver_dir.mkdir(parents=True, exist_ok=True)
    path = solver_dir / f"session_{slug}.jsonl"
    parent = parent_session or _current_session_dir.name
    _solver_session_meta = {
        "source": "solver",
        "started_at": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "parent_session": parent,
        "id": path.stem,
        "origin": "subagent",
    }
    _write_jsonl_meta(path, _solver_session_meta)
    _solver_session = path
    append_parent_event(
        {
            "type": "subagent/start",
            "name": "solver",
            "path": f"solver/{path.name}",
            "parent_session": parent,
        }
    )
    print(f"  \033[90m[solver-memory] .memory/{_current_session_dir.name}/solver/{path.name}\033[0m")
    return path


def sync_solver_session_messages(messages: list, *, reason: str = "") -> None:
    global _solver_session
    if _solver_session is None:
        start_solver_session()
    assert _solver_session is not None
    tag = f" ({reason})" if reason else ""
    new_events: list[dict] = []
    for msg in messages:
        new_events.extend(_msg_to_events(msg))
    existing = read_jsonl_events(_solver_session)
    for e in existing:
        if isinstance(e, dict):
            _note_event_ts(_solver_session, e.get("ts"))
    seen = {_event_fingerprint(e) for e in existing}
    added = 0
    for ev in new_events:
        fp = _event_fingerprint(ev)
        if fp in seen:
            continue
        # 批量落盘时也保证条间至少隔 1ms，避免全挤在同一秒
        append_jsonl_event(_solver_session, ev)
        seen.add(fp)
        added += 1
    if added:
        print(f"  \033[90m[solver-memory] 会话已写入 +{added} 条{tag}\033[0m")


def end_solver_session(*, summary: str = "") -> None:
    global _solver_session, _solver_session_meta
    if _solver_session is not None:
        append_parent_event(
            {
                "type": "subagent/end",
                "name": "solver",
                "path": f"solver/{_solver_session.name}",
                "summary": (summary or "")[:2000],
            }
        )
        print(f"  \033[90m[solver-memory] 结束: {_solver_session.name}\033[0m")
    _solver_session = None
    _solver_session_meta = {}


def current_solver_session_name() -> str:
    return _solver_session.name if _solver_session else "（尚无 Solver 会话）"


def record_turn(user_query: str, assistant_summary: str) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    msgs = []
    if (user_query or "").strip():
        msgs.append(HumanMessage(content=user_query.strip()))
    if (assistant_summary or "").strip():
        msgs.append(AIMessage(content=assistant_summary.strip()))
    if msgs:
        sync_session_messages(msgs, reason="record_turn")


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
    folder = MEMORY_DIR / name
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
        # session_xxx/session.jsonl
        folder, _ = name.split("/", 1)
        path = MEMORY_DIR / folder / SESSION_JSONL
        if path.exists():
            return path

    if "/solver/" in name:
        # session_xxx/solver/session_yyy.jsonl
        parts = name.split("/")
        if len(parts) == 3:
            path = MEMORY_DIR / parts[0] / "solver" / parts[2]
            if path.exists():
                return path

    if name.startswith("solver/") and _current_session_dir is not None:
        path = _current_session_dir / name
        if path.exists():
            return path

    # 仅文件夹名
    if name.startswith("session_") and "/" not in name:
        path = MEMORY_DIR / name / SESSION_JSONL
        if path.exists():
            return path
        # 可能是 solver 文件名：在各会话 solver/ 下找
        for d in iter_session_dirs():
            cand = d / "solver" / name
            if cand.exists():
                return cand
            if not name.endswith(".jsonl"):
                cand = d / "solver" / f"{name}.jsonl"
                if cand.exists():
                    return cand

    if name.endswith(".jsonl") and _current_session_dir is not None:
        cand = _current_session_dir / "solver" / name
        if cand.exists():
            return cand

    raise FileNotFoundError(name)


def get_session_events(name: str) -> list[dict]:
    path = resolve_session_jsonl(name)
    return read_jsonl_events(path)


def current_session_log_text() -> str:
    if _current_session is None or not _current_session.exists():
        return ""
    return _current_session.read_text(encoding="utf-8")


def current_session_dir_name() -> str:
    return _current_session_dir.name if _current_session_dir else ""


def _extract_section(md: str, heading: str) -> str:
    aliases = {
        "记忆种类与目的": ["记忆种类与目的", "第0层：记忆种类与目的"],
        "用户画像与偏好": ["用户画像与偏好", "第三层：用户画像与偏好"],
        "短期记忆": ["短期记忆", "第一层：短期记忆"],
        "长期记忆": ["长期记忆", "第二层：长期记忆"],
    }
    names = aliases.get(heading, [heading])
    for name in names:
        pattern = rf"^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)"
        m = re.search(pattern, md, re.M | re.S)
        if m:
            return m.group(1).strip()
    return ""


def memory_core_for_prompt() -> str:
    ensure_memory_files()
    raw = MEMORY_FILE.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    kinds = _extract_section(body if meta else raw, "记忆种类与目的")
    profile = _extract_section(body if meta else raw, "用户画像与偏好")
    parts = []
    desc = meta.get("description") or "用户分层记忆；短期/长期请 load_memory 按需加载。"
    parts.append(f"**说明**：{desc}")
    if kinds:
        parts.append("### 记忆种类与目的\n" + kinds)
    if profile:
        parts.append("### 用户画像与偏好\n" + profile)
    if not kinds and not profile:
        parts.append("（MEMORY.md 暂无种类/画像内容）")
    return "\n\n".join(parts)


def load_memory_layer(layer: str, *, limit: int = 8000) -> str:
    ensure_memory_files()
    key = (layer or "").strip().lower()
    raw = MEMORY_FILE.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    src = body if meta else raw

    if key in ("core", "default"):
        return memory_core_for_prompt()
    if key in ("kinds", "kind", "catalog", "index"):
        return _extract_section(src, "记忆种类与目的") or "（无记忆种类表）"
    if key in ("profile", "pref", "preferences", "l3"):
        return _extract_section(src, "用户画像与偏好") or "（无用户画像与偏好）"
    if key in ("short", "short_term", "l1"):
        parts = []
        if _short_term:
            lines = []
            for i, item in enumerate(_short_term, 1):
                lines.append(f"{i}. 问：{item['user'][:200]}")
                if item.get("summary"):
                    lines.append(f"   答要：{item['summary'][:400]}")
            parts.append("【本进程工作记忆】\n" + "\n".join(lines))
        sec = _extract_section(src, "短期记忆")
        if sec and "（最近约三次" not in sec and "暂无" not in sec:
            parts.append("【MEMORY.md · 短期记忆】\n" + sec)
        return ("\n\n".join(parts) if parts else "（无短期记忆）")[:limit]
    if key in ("long", "long_term", "l2"):
        return (_extract_section(src, "长期记忆") or "（无长期记忆）")[:limit]
    if key in ("all", "full"):
        return raw.strip()[: max(limit, 12000)]
    return f"错误：未知 layer={layer!r}。可用：core / kinds / profile / short / long / all"


def current_session_name() -> str:
    if _current_session_dir is not None:
        return _current_session_dir.name
    return "（尚未选择会话）"
