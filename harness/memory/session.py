"""Planner 会话生命周期：新建、续聊、落盘。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from harness.memory import paths, runtime
from harness.memory.constants import SESSION_JSONL
from harness.memory.files import ensure_memory_files
from harness.memory.jsonl import (
    append_jsonl_event,
    event_fingerprint,
    is_session_dir,
    iter_session_dirs,
    load_session_view,
    msg_to_events,
    read_jsonl_events,
    session_has_dialogue,
    strip_session_name,
    write_jsonl_meta,
)


def set_thread_id(thread_id: str) -> None:
    import harness.config as cfg

    cfg.THREAD_ID = (thread_id or "").strip() or cfg.THREAD_ID


def rebuild_short_term_from_view(view: dict) -> None:
    runtime.short_term.clear()
    for entry in view.get("messages") or []:
        if not isinstance(entry, dict):
            continue
        if "HumanMessage" in entry:
            q = entry["HumanMessage"]
            if isinstance(q, str) and q.strip():
                runtime.short_term.append({"user": q.strip()[:500], "summary": ""})
        elif "AIMessage" in entry and runtime.short_term:
            v = entry["AIMessage"]
            text = v.get("content", "") if isinstance(v, dict) else str(v)
            runtime.short_term[-1]["summary"] = (text or "")[:800]


def activate_session_dir(session_dir: Path, *, source: str, resume: bool) -> Path:
    jsonl = session_dir / SESSION_JSONL
    view = load_session_view(session_dir)
    thread_id = str(view.get("thread_id") or session_dir.name)
    set_thread_id(thread_id)
    runtime.current_session_dir = session_dir
    runtime.current_session = jsonl
    runtime.session_started_at = str(view.get("started_at") or "")
    runtime.session_meta = {
        "source": view.get("source") or source,
        "started_at": runtime.session_started_at,
        "thread_id": thread_id,
        "id": session_dir.name,
    }
    if resume:
        append_jsonl_event(
            jsonl,
            {
                "type": "session/meta",
                "source": runtime.session_meta["source"],
                "started_at": runtime.session_started_at,
                "thread_id": thread_id,
                "id": session_dir.name,
                "resumed": True,
            },
        )
        rebuild_short_term_from_view(view)
    else:
        runtime.short_term.clear()
    return jsonl


def create_new_session(source: str = "cli") -> Path:
    """新建会话目录；thread_id = 目录名（进程内）。"""
    ensure_memory_files()
    runtime.short_term.clear()

    ts = datetime.now()
    runtime.session_started_at = ts.strftime("%Y-%m-%d %H:%M:%S")
    slug = ts.strftime("%Y%m%d_%H%M%S_%f")
    session_dir = paths.MEMORY_DIR / f"session_{slug}"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "solver").mkdir(exist_ok=True)
    jsonl = session_dir / SESSION_JSONL
    thread_id = session_dir.name
    set_thread_id(thread_id)

    runtime.session_meta = {
        "source": source,
        "started_at": runtime.session_started_at,
        "thread_id": thread_id,
        "id": session_dir.name,
    }
    write_jsonl_meta(jsonl, runtime.session_meta)
    runtime.current_session_dir = session_dir
    runtime.current_session = jsonl
    print(f"  \033[90m[memory] 新会话: .memory/{session_dir.name}/\033[0m")
    return jsonl


def resume_session(name: str, *, source: str = "cli") -> Path:
    """打开已有会话目录。"""
    ensure_memory_files()
    name = strip_session_name(name)
    if "/" in name or ".." in name or not name.startswith("session_"):
        raise ValueError(f"非法会话名: {name}")
    session_dir = paths.MEMORY_DIR / name
    if not is_session_dir(session_dir):
        raise FileNotFoundError(f"会话不存在: {name}")
    jsonl = activate_session_dir(session_dir, source=source, resume=True)
    n = len(load_session_view(session_dir).get("messages") or [])
    print(f"  \033[90m[memory] 续聊: .memory/{session_dir.name}/（已有 {n} 条消息）\033[0m")
    return jsonl


def prompt_choose_session(*, source: str = "cli") -> Path:
    """交互：新建或选择已有会话。非 TTY 时默认新建。"""
    import sys

    from harness.memory.consolidate import compress_session, consolidate_session, session_needs_compress

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
            if session_has_dialogue(chosen):
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
    return runtime.current_session is not None


def note_short_term(ev: dict) -> None:
    if ev.get("type") == "user/message":
        q = ev.get("text") or ""
        if isinstance(q, str) and q.strip():
            runtime.short_term.append({"user": q.strip()[:500], "summary": ""})
    elif ev.get("type") == "assistant/message" and runtime.short_term:
        runtime.short_term[-1]["summary"] = (ev.get("text") or "")[:800]


def sync_session_messages(messages: list, *, reason: str = "") -> None:
    if runtime.current_session is None:
        raise RuntimeError("尚未选择会话：请先 start_session / create_new_session / resume_session")

    tag = f" ({reason})" if reason else ""
    new_events: list[dict] = []
    for msg in messages:
        new_events.extend(msg_to_events(msg))

    existing = read_jsonl_events(runtime.current_session)
    seen = {event_fingerprint(e) for e in existing}
    added = 0
    for ev in new_events:
        fp = event_fingerprint(ev)
        if fp in seen:
            continue
        append_jsonl_event(runtime.current_session, ev)
        seen.add(fp)
        added += 1
        note_short_term(ev)
    if added:
        print(f"  \033[90m[memory] 会话已写入 +{added} 条{tag}\033[0m")


def append_parent_event(event: dict) -> None:
    if runtime.current_session is None:
        return
    append_jsonl_event(runtime.current_session, event)


def record_turn(user_query: str, assistant_summary: str) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    msgs = []
    if (user_query or "").strip():
        msgs.append(HumanMessage(content=user_query.strip()))
    if (assistant_summary or "").strip():
        msgs.append(AIMessage(content=assistant_summary.strip()))
    if msgs:
        sync_session_messages(msgs, reason="record_turn")


def current_session_name() -> str:
    if runtime.current_session_dir is not None:
        return runtime.current_session_dir.name
    return "（尚未选择会话）"


def current_session_dir_name() -> str:
    return runtime.current_session_dir.name if runtime.current_session_dir else ""


def current_session_log_text() -> str:
    if runtime.current_session is None or not runtime.current_session.exists():
        return ""
    return runtime.current_session.read_text(encoding="utf-8")
