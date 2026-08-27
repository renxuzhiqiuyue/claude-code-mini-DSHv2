"""load_skill：按角色从 skills/{planner|solver}/ + shared/ 加载 SKILL.md。"""

from __future__ import annotations

from langchain_core.tools import tool

from harness.skills import load_skill_content, scan_skills


def _run(name: str, role: str) -> str:
    print(f"\033[33m→ load_skill({name!r}, role={role})\033[0m")
    scan_skills(role)
    out = load_skill_content(name, role=role)
    print(out[:200] + ("..." if len(out) > 200 else ""))
    return out


@tool("load_skill")
def load_skill(name: str) -> str:
    """（Planner）按名称加载技能全文。仅可见 skills/planner/ 与 skills/shared/。"""
    return _run(name, "planner")


@tool("load_skill")
def load_skill_solver(name: str) -> str:
    """（Solver）按名称加载技能全文。仅可见 skills/solver/ 与 skills/shared/。"""
    return _run(name, "solver")
