"""Planner @dynamic_prompt（委托 agents.prompts 统一模板）。"""

from __future__ import annotations

from langchain.agents.middleware import ModelRequest, dynamic_prompt

from agents.prompts import build_planner_system_prompt


@dynamic_prompt
def harness_system_prompt(request: ModelRequest) -> str:
    msgs = getattr(request, "messages", None) or []
    return build_planner_system_prompt(message_count=len(msgs))
