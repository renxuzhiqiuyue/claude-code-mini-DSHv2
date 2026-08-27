"""s08 → @before_model 压缩；Todo 提醒一并注入。"""

from __future__ import annotations

import json
from typing import Any

from langchain.agents.middleware import AgentState, before_model
from langchain_core.messages import HumanMessage, RemoveMessage, message_to_dict
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime

from harness.compaction import context_char_limit, estimate_size, prepare_context, todo_nag_rounds
from harness.todo import bump_todo_round, reset_todo_round, should_nag_todo


def _serialize(messages: list) -> str:
    return json.dumps([message_to_dict(m) for m in messages], default=str)


@before_model
def compaction_middleware(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    messages = list(state["messages"])
    before = _serialize(messages)

    bump_todo_round()
    if should_nag_todo(todo_nag_rounds()):
        messages.append(
            HumanMessage(
                content="<reminder>请使用 todo_write 更新待办进度后再继续。</reminder>"
            )
        )
        reset_todo_round()
        print("  \033[36m[todo] 已注入待办提醒\033[0m")

    size_before = estimate_size(messages)
    prepare_context(messages)
    after = _serialize(messages)
    if before != after:
        print(
            f"  \033[36m[compact] 上下文已压缩"
            f"（{size_before} → {estimate_size(messages)} 字符，"
            f"阈值 {context_char_limit()}）\033[0m"
        )
        return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *messages]}
    return None
