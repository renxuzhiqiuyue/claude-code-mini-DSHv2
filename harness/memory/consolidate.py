"""将会话总结进 MEMORY.md，或把历史压成摘要。"""

from __future__ import annotations

import re
from datetime import datetime

from harness.memory import paths, runtime
from harness.memory.constants import SESSION_COMPRESS_USER_TEXT, SESSION_JSONL
from harness.memory.files import ensure_memory_files, mark_consolidated
from harness.memory.jsonl import (
    count_dialogue_events,
    initial_session_meta,
    is_session_dir,
    load_session_view,
    read_jsonl_events,
    rewrite_session_jsonl,
    session_as_dialogue_text,
    session_has_dialogue,
    session_is_compressed_only,
    strip_session_name,
)


def session_needs_compress(session_name: str) -> bool:
    """是否仍有可压缩的历史对话（已压缩为摘要对则不再提示）。"""
    name = strip_session_name(session_name)
    session_dir = paths.MEMORY_DIR / name
    if not is_session_dir(session_dir):
        return False
    events = read_jsonl_events(session_dir / SESSION_JSONL)
    if not session_has_dialogue(session_dir):
        return False
    if session_is_compressed_only(events):
        return False
    return count_dialogue_events(events) > 0


def consolidate_session(session_name: str) -> dict:
    """将指定会话目录总结进 MEMORY.md。

    Returns:
        {"ok": bool, "updated": bool, "message": str, "session": str}
    """
    ensure_memory_files()
    name = strip_session_name(session_name)
    if "/" in name or ".." in name or not name.startswith("session_"):
        return {"ok": False, "updated": False, "message": f"非法会话名: {session_name}", "session": name}

    session_dir = paths.MEMORY_DIR / name
    if not is_session_dir(session_dir):
        return {"ok": False, "updated": False, "message": f"会话不存在: {name}", "session": name}

    if not session_has_dialogue(session_dir):
        mark_consolidated(name, updated=False)
        return {
            "ok": True,
            "updated": False,
            "message": "该会话无可总结的对话",
            "session": name,
        }

    dialogue = session_as_dialogue_text(session_dir)
    memory = paths.MEMORY_FILE.read_text(encoding="utf-8")
    print(f"  \033[36m[memory] 总结会话 {name} → MEMORY.md …\033[0m")
    try:
        from agents.agent import run_memory_consolidation

        text = run_memory_consolidation(memory=memory, dialogue=dialogue[:80000])
    except Exception as e:
        msg = f"模型更新失败: {e}"
        print(f"  \033[31m[memory] {msg}\033[0m")
        return {"ok": False, "updated": False, "message": msg, "session": name}

    if not text or "[[NO_UPDATE]]" in text.splitlines()[0] or text.strip() == "[[NO_UPDATE]]":
        mark_consolidated(name, updated=False)
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

    paths.MEMORY_FILE.write_text(text.rstrip() + "\n", encoding="utf-8")
    mark_consolidated(name, updated=True)
    print("  \033[32m[memory] MEMORY.md 已由模型增量更新\033[0m")
    return {
        "ok": True,
        "updated": True,
        "message": "已将会话要点写入 MEMORY.md",
        "session": name,
    }


def compress_session(session_name: str) -> dict:
    """将历史会话压成「用户压缩请求 + 助手摘要」两条消息，重写 session.jsonl。

    Returns:
        {"ok": bool, "compressed": bool, "message": str, "session": str, "summary": str}
    """
    from harness.memory.session import rebuild_short_term_from_view

    ensure_memory_files()
    name = strip_session_name(session_name)
    if "/" in name or ".." in name or not name.startswith("session_"):
        return {
            "ok": False,
            "compressed": False,
            "message": f"非法会话名: {session_name}",
            "session": name,
            "summary": "",
        }

    session_dir = paths.MEMORY_DIR / name
    if not is_session_dir(session_dir):
        return {
            "ok": False,
            "compressed": False,
            "message": f"会话不存在: {name}",
            "session": name,
            "summary": "",
        }

    jsonl = session_dir / SESSION_JSONL
    events = read_jsonl_events(jsonl)
    if not session_has_dialogue(session_dir):
        return {
            "ok": True,
            "compressed": False,
            "message": "该会话无可压缩的对话",
            "session": name,
            "summary": "",
        }
    if session_is_compressed_only(events):
        return {
            "ok": True,
            "compressed": False,
            "message": "会话已是压缩摘要，无需重复",
            "session": name,
            "summary": "",
        }

    dialogue = session_as_dialogue_text(session_dir)
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

    meta = initial_session_meta(events) or {
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
    rewrite_session_jsonl(jsonl, new_events)

    if runtime.current_session_dir and runtime.current_session_dir.name == name:
        runtime.current_session = jsonl
        view = load_session_view(session_dir)
        rebuild_short_term_from_view(view)

    print(f"  \033[32m[memory] 会话 {name} 历史已压缩为摘要\033[0m")
    return {
        "ok": True,
        "compressed": True,
        "message": "历史会话已压缩为摘要",
        "session": name,
        "summary": summary.strip()[:500],
    }
