"""create_agent 组装 — Planner（主）/ Solver / Memory Consolidation。"""

from __future__ import annotations

import os
import re

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from agents.llm import make_llm, make_memory_llm, make_solver_llm
from agents.middleware import MIDDLEWARE_STACK
from agents.middleware.permission import solver_permission_middleware
from agents.middleware.recovery import error_recovery_middleware
from agents.prompts import build_memory_consolidate_prompt, build_session_compress_prompt
from harness.skills import scan_skills
from tools import PLANNER_TOOLS, SOLVER_TOOLS

_solver_llm_ready = False


def warm_solver() -> None:
    """进程启动时预检 Solver 模型配置（真正图在 solve_task 时创建并销毁）。"""
    global _solver_llm_ready
    scan_skills()  # 预扫 planner + solver
    make_solver_llm()
    _solver_llm_ready = True
    print(
        f"  Planner 模型: {os.getenv('Planner_MODEL_ID', '').strip()}\n"
        f"  Solver 模型:  {os.getenv('Solver_MODEL_ID', '').strip()}\n"
        f"  Memory 模型:  {os.getenv('Memory_MODEL_ID', '').strip()}"
    )


def build_planner():
    """对外主智能体 = Planner（进程内 InMemory，不落盘 checkpoint）。"""
    scan_skills()
    warm_solver()
    return create_agent(
        model=make_llm(),
        tools=PLANNER_TOOLS,
        middleware=MIDDLEWARE_STACK,
        checkpointer=InMemorySaver(),
        system_prompt="占位：由动态 prompt middleware（Planner）覆盖。",
    )


def build_agent():
    """兼容旧入口 → Planner。"""
    return build_planner()


def build_solver_agent(system_prompt: str):
    """供 solve_task 使用；一般不要直接对外暴露。"""
    from agents.middleware.lifecycle import (
        solver_session_on_ai,
        solver_session_on_turn,
        solver_session_on_user,
    )

    scan_skills()
    return create_agent(
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
        system_prompt=system_prompt,
    )


def run_memory_consolidation(*, memory: str, dialogue: str) -> str:
    """记忆整理：无工具，单次 invoke；返回模型原文（可能是 MEMORY.md 或 [[NO_UPDATE]]）。"""
    llm = make_memory_llm()
    prompt = build_memory_consolidate_prompt(memory=memory, dialogue=dialogue)
    resp = llm.invoke([HumanMessage(content=prompt)])
    content = resp.content
    if isinstance(content, list):
        content = "\n".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )
    return str(content).strip()


def run_session_compression(*, dialogue: str) -> str:
    """会话历史压缩：无工具，单次 invoke；返回摘要正文。"""
    llm = make_memory_llm()
    prompt = build_session_compress_prompt(dialogue=dialogue)
    resp = llm.invoke([HumanMessage(content=prompt)])
    content = resp.content
    if isinstance(content, list):
        content = "\n".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )
    text = str(content).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:\w+)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()
