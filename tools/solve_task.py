"""solve_task：把单个未完成待办交给 Solver 智能体执行，返回总结后销毁本次 Solver。"""

from __future__ import annotations

import os
import threading

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from harness.todo import format_todo_item, next_todo_for_solver, unfinished_todos

_solve_task_lock = threading.Lock()


def _solver_system_prompt(task_block: str) -> str:
    from agents.prompts import build_solver_system_prompt

    return build_solver_system_prompt(task_block)


def _run_solver(task_block: str) -> str:
    from langchain.agents import create_agent
    from langgraph.checkpoint.memory import InMemorySaver

    from agents.llm import make_solver_llm
    from agents.middleware.lifecycle import (
        solver_session_on_ai,
        solver_session_on_turn,
        solver_session_on_user,
    )
    from agents.middleware.permission import solver_permission_middleware
    from agents.middleware.recovery import error_recovery_middleware
    from harness.memory import (
        current_session_name,
        end_solver_session,
        start_solver_session,
        sync_solver_session_messages,
    )
    from tools import SOLVER_TOOLS

    model_id = (os.getenv("Solver_MODEL_ID") or "").strip()
    print(f"\n\033[35m[Solver 启动] model={model_id or '(unset)'}\033[0m")
    start_solver_session(parent_session=current_session_name())
    try:
        solver = create_agent(
            model=make_solver_llm(),
            tools=SOLVER_TOOLS,
            middleware=[
                solver_session_on_user,
                error_recovery_middleware,
                solver_session_on_ai,
                solver_permission_middleware,
                solver_session_on_turn,
            ],
            checkpointer=InMemorySaver(),
            system_prompt=_solver_system_prompt(task_block),
        )
        result = solver.invoke(
            {"messages": [HumanMessage(content=f"请执行下列任务并总结结果：\n{task_block}")]},
            config={"configurable": {"thread_id": f"solver-{abs(hash(task_block)) % 100_000}"}},
        )
        try:
            sync_solver_session_messages(result.get("messages") or [], reason="final")
        except Exception as e:
            print(f"  \033[31m[solver-memory] 收尾写入失败: {e}\033[0m")

        text = ""
        for m in reversed(result["messages"]):
            if isinstance(m, AIMessage) and m.content and not m.tool_calls:
                c = m.content
                text = c if isinstance(c, str) else str(c)
                break
        if not text:
            text = "Solver 未返回文本结论。"
        end_solver_session(summary=text)
        print("\033[35m[Solver 结束并销毁]\033[0m")
        return text
    except Exception:
        end_solver_session(summary="")
        print("\033[35m[Solver 结束并销毁]\033[0m")
        raise


@tool("solve_task")
def solve_task(description: str = "") -> str:
    """将**一个**未完成待办交给 Solver 执行并返回总结（每次调用仅委派一项）。

    多步骤任务须先 todo_write 拆分，每次只将一个待办标为 in_progress 再调用本工具；
    须等 Solver 返回后，再 solve_task 委派下一项。禁止一次委派多个步骤或在同一轮多次调用。

    description 可补充该步骤的上下文；若无未完成待办，则仅执行 description（仍须为单一任务）。
    Solver 读 Solver_*；轨迹写入当前会话目录 `.memory/session_*/solver/*.jsonl`；跑完即销毁。
    """
    if not _solve_task_lock.acquire(blocking=False):
        return "错误：已有 Solver 任务在执行中，请等待其完成后再委派下一项。"

    try:
        pending = unfinished_todos()
        next_todo = next_todo_for_solver()
        parts = []
        if next_todo:
            parts.append("【本次委派待办（仅此一项）】\n" + format_todo_item(next_todo))
            if len(pending) > 1:
                parts.append(
                    f"（提示：另有 {len(pending) - 1} 项未完成；"
                    "Planner 须在本轮 Solver 结束后再逐项 solve_task，勿一次委派多项）"
                )
        desc = (description or "").strip()
        if desc:
            parts.append("【补充说明】\n" + desc)
        if not parts:
            return "错误：没有未完成待办，且未提供 description。请先 todo_write 或传入单一任务说明。"
        task_block = "\n\n".join(parts)
        preview = task_block.replace("\n", " ")[:100]
        print(f"\033[33m→ solve_task({preview!r}...)\033[0m")
        return _run_solver(task_block)
    finally:
        _solve_task_lock.release()
