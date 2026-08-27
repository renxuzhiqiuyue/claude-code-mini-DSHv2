"""Phase B middleware 栈。"""

from __future__ import annotations

from agents.middleware.compaction import compaction_middleware
from agents.middleware.lifecycle import (
    memory_and_stop_middleware,
    session_on_ai_done,
    session_on_user_ask,
)
from agents.middleware.permission import permission_middleware, solver_permission_middleware
from agents.middleware.prompt import harness_system_prompt
from agents.middleware.recovery import error_recovery_middleware

MIDDLEWARE_STACK = [
    session_on_user_ask,         # @before_agent — 用户询问写入 session.json
    compaction_middleware,       # @before_model — 字符超限裁剪 + todo 提醒
    harness_system_prompt,       # @dynamic_prompt — Planner system
    error_recovery_middleware,   # @wrap_model_call — 429/529 重试
    session_on_ai_done,          # @after_model — AI 生成写入 session.json
    permission_middleware,       # @wrap_tool_call — 权限 + ToolMessage 写入
    memory_and_stop_middleware,  # @after_agent — 收尾全量同步
]

__all__ = [
    "MIDDLEWARE_STACK",
    "permission_middleware",
    "solver_permission_middleware",
]
