"""权限 → @wrap_tool_call；工具结果写入 session JSON；重置 todo 计数。"""

from __future__ import annotations

from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage

from harness.memory import sync_session_messages
from harness.permission import check_tool_permission
from harness.todo import reset_todo_round


@wrap_tool_call
def permission_middleware(request, handler):
    name = request.tool_call["name"]
    args = request.tool_call.get("args") or {}
    denied = check_tool_permission(name, args)
    if denied:
        print(f"  \033[31m[权限] 拒绝 {name}: {denied}\033[0m")
        result = ToolMessage(
            content=denied,
            tool_call_id=request.tool_call["id"],
            name=name,
            status="error",
        )
    else:
        result = handler(request)
        if name == "todo_write":
            reset_todo_round()

    try:
        state = getattr(request, "state", None) or {}
        msgs = list(state.get("messages") or [])
        if isinstance(result, ToolMessage):
            sync_session_messages(msgs + [result], reason="tool")
    except Exception as e:
        print(f"  \033[31m[memory] 写入失败(tool): {e}\033[0m")
    return result


@wrap_tool_call
def solver_permission_middleware(request, handler):
    """Solver：路径/破坏性权限；写入 .memory/solver/session；禁止读 MEMORY/主 session。"""
    name = request.tool_call["name"]
    args = request.tool_call.get("args") or {}

    if name == "load_memory":
        return ToolMessage(
            content="权限拒绝：Solver 不得读取用户记忆",
            tool_call_id=request.tool_call["id"],
            name=name,
            status="error",
        )

    # 禁止经 bash 逃逸访问记忆目录
    if name == "bash":
        cmd = str(args.get("command") or "")
        if ".memory" in cmd.replace("\\", "/"):
            return ToolMessage(
                content="权限拒绝：Solver 禁止访问 .memory/",
                tool_call_id=request.tool_call["id"],
                name=name,
                status="error",
            )

    denied = check_tool_permission(name, args)
    if denied:
        print(f"  \033[31m[Solver权限] 拒绝 {name}: {denied}\033[0m")
        result = ToolMessage(
            content=denied,
            tool_call_id=request.tool_call["id"],
            name=name,
            status="error",
        )
    else:
        result = handler(request)

    try:
        from harness.memory import sync_solver_session_messages

        state = getattr(request, "state", None) or {}
        msgs = list(state.get("messages") or [])
        if isinstance(result, ToolMessage):
            sync_solver_session_messages(msgs + [result], reason="tool")
    except Exception as e:
        print(f"  \033[31m[solver-memory] 写入失败(tool): {e}\033[0m")
    return result
