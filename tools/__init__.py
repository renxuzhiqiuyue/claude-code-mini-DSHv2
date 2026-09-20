"""LangChain @tool 汇总。

Planner（主）与 Solver 使用不同工具集。
"""

from __future__ import annotations

from tools.bash import bash
from tools.filesystem import edit_file, read_file, write_file
from tools.load_memory import load_memory
from tools.load_skill import load_skill, load_skill_solver
from tools.local_tools import LOCAL_TOOLS, calculator, current_date
from tools.root_cause import build_root_cause_tree, fetch_period_data
from tools.solve_task import solve_task
from tools.tavily_search import tavily_search
from tools.text2sql import (
    sql_db_list_tables,
    sql_db_query,
    sql_db_query_checker,
    sql_db_table_schema,
)
from tools.todo_write import todo_write

# Planner：规划 + 简单动手 + 委派 Solver + 本地工具
PLANNER_TOOLS = [
    bash,
    read_file,
    write_file,
    edit_file,
    todo_write,
    load_skill,
    load_memory,
    solve_task,
    tavily_search,
    *LOCAL_TOOLS,
]

# Solver：执行向（无 todo_write / solve_task / load_memory；技能仅 solver+shared）
SOLVER_TOOLS = [
    bash,
    read_file,
    write_file,
    edit_file,
    load_skill_solver,
    tavily_search,
    sql_db_list_tables,
    sql_db_table_schema,
    sql_db_query_checker,
    sql_db_query,
    fetch_period_data,
    build_root_cause_tree,
    *LOCAL_TOOLS,
]

# 兼容旧名：默认指 Planner 工具
TOOLS = PLANNER_TOOLS
BASIC_TOOLS = PLANNER_TOOLS

__all__ = [
    "TOOLS",
    "BASIC_TOOLS",
    "PLANNER_TOOLS",
    "SOLVER_TOOLS",
    "LOCAL_TOOLS",
    "bash",
    "read_file",
    "write_file",
    "edit_file",
    "todo_write",
    "load_skill",
    "load_skill_solver",
    "load_memory",
    "solve_task",
    "sql_db_list_tables",
    "sql_db_table_schema",
    "sql_db_query_checker",
    "sql_db_query",
    "fetch_period_data",
    "build_root_cause_tree",
    "tavily_search",
    "current_date",
    "calculator",
]
