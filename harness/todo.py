"""Todo 状态（进程内）。"""

from __future__ import annotations

CURRENT_TODOS: list[dict] = []
ROUNDS_SINCE_TODO = 0


def run_todo_write(todos: list) -> str:
    global CURRENT_TODOS, ROUNDS_SINCE_TODO
    CURRENT_TODOS = list(todos or [])
    ROUNDS_SINCE_TODO = 0
    icons = {"pending": " ", "in_progress": "▸", "completed": "✓"}
    lines = []
    for t in CURRENT_TODOS:
        status = t.get("status", "pending")
        content = t.get("content", "")
        icon = icons.get(status, "?")
        line = f"  [{icon}] {content}"
        print(line)
        lines.append(line)
    return f"已更新 {len(CURRENT_TODOS)} 项待办"


def bump_todo_round() -> None:
    global ROUNDS_SINCE_TODO
    ROUNDS_SINCE_TODO += 1


def reset_todo_round() -> None:
    global ROUNDS_SINCE_TODO
    ROUNDS_SINCE_TODO = 0


def should_nag_todo(threshold: int = 3) -> bool:
    return ROUNDS_SINCE_TODO >= threshold


def unfinished_todos() -> list[dict]:
    """pending / in_progress 待办，供 Solver 领取。"""
    out = []
    for t in CURRENT_TODOS:
        status = (t.get("status") or "pending").lower()
        if status in ("pending", "in_progress"):
            out.append(t)
    return out


def next_todo_for_solver() -> dict | None:
    """供 Solver 领取的单一待办：优先 in_progress，否则首个 pending。"""
    first_pending: dict | None = None
    for t in CURRENT_TODOS:
        status = (t.get("status") or "pending").lower()
        if status == "in_progress":
            return t
        if status == "pending" and first_pending is None:
            first_pending = t
    return first_pending


def format_todo_item(t: dict) -> str:
    return f"[{t.get('status', 'pending')}] {t.get('content', '')}"


def format_unfinished_todos() -> str:
    items = unfinished_todos()
    if not items:
        return "（当前没有 pending / in_progress 待办）"
    lines = []
    for i, t in enumerate(items, 1):
        lines.append(f"{i}. [{t.get('status', 'pending')}] {t.get('content', '')}")
    return "\n".join(lines)
