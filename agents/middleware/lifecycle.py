"""会话落盘：写入当前 `.memory/session_*/session.jsonl`。"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentState, after_agent, after_model, before_agent
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime

from harness.memory import sync_session_messages, sync_solver_session_messages


@before_agent
def session_on_user_ask(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """用户本轮询问进入 Agent 时写入 HumanMessage。"""
    try:
        sync_session_messages(state.get("messages") or [], reason="user")
    except Exception as e:
        print(f"  \033[31m[memory] 写入失败(user): {e}\033[0m")
    return None


@after_model
def session_on_ai_done(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """模型生成结束时写入 AIMessage（及已有消息）。"""
    try:
        sync_session_messages(state.get("messages") or [], reason="ai")
    except Exception as e:
        print(f"  \033[31m[memory] 写入失败(ai): {e}\033[0m")
    return None


@after_agent
def memory_and_stop_middleware(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    messages = state.get("messages") or []
    tool_count = sum(1 for m in messages if isinstance(m, ToolMessage))
    print(f"\033[90m[stop] 本轮共 {tool_count} 条工具结果\033[0m")
    try:
        sync_session_messages(messages, reason="turn")
    except Exception as e:
        print(f"  \033[31m[memory] 写入失败(turn): {e}\033[0m")
    return None


@before_agent
def solver_session_on_user(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    try:
        sync_solver_session_messages(state.get("messages") or [], reason="user")
    except Exception as e:
        print(f"  \033[31m[solver-memory] 写入失败(user): {e}\033[0m")
    return None


@after_model
def solver_session_on_ai(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    try:
        sync_solver_session_messages(state.get("messages") or [], reason="ai")
    except Exception as e:
        print(f"  \033[31m[solver-memory] 写入失败(ai): {e}\033[0m")
    return None


@after_agent
def solver_session_on_turn(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    try:
        sync_solver_session_messages(state.get("messages") or [], reason="turn")
    except Exception as e:
        print(f"  \033[31m[solver-memory] 写入失败(turn): {e}\033[0m")
    return None
