"""LLM：ChatOpenAI。Planner / Solver 各自 os.getenv 读 .env。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True, interpolate=True)


def make_llm() -> ChatOpenAI:
    """Planner 模型。"""
    return ChatOpenAI(
        model=os.getenv("Planner_MODEL_ID"),
        api_key=os.getenv("Planner_API_KEY"),
        base_url=os.getenv("Planner_BASE_URL"),
        temperature=float(os.getenv("LLM_TEMPERATURE")),
        max_tokens=int(os.getenv("DEFAULT_MAX_TOKENS")),
    )


def make_solver_llm() -> ChatOpenAI:
    """Solver 模型。"""
    return ChatOpenAI(
        model=os.getenv("Solver_MODEL_ID"),
        api_key=os.getenv("Solver_API_KEY"),
        base_url=os.getenv("Solver_BASE_URL"),
        temperature=float(os.getenv("LLM_TEMPERATURE")),
        max_tokens=int(os.getenv("DEFAULT_MAX_TOKENS")),
    )


def make_memory_llm() -> ChatOpenAI:
    """记忆整理专用模型。"""
    return ChatOpenAI(
        model=os.getenv("Memory_MODEL_ID"),
        api_key=os.getenv("Memory_API_KEY"),
        base_url=os.getenv("Memory_BASE_URL"),
        temperature=float(os.getenv("LLM_TEMPERATURE")),
        max_tokens=int(os.getenv("DEFAULT_MAX_TOKENS")),
    )
