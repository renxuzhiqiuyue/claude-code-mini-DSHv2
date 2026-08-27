"""todo_write：更新进程内待办列表。"""

from __future__ import annotations

from langchain_core.tools import tool

from harness.todo import run_todo_write


@tool("todo_write")
def todo_write(todos: list) -> str:
    """更新待办列表。每项含 content 与 status（pending|in_progress|completed）。多步骤任务开始前请先调用。"""
    print("\033[33m→ todo_write\033[0m")
    if isinstance(todos, dict):
        todos = todos.get("todos", [todos])
    return run_todo_write(todos)
