"""text2sql：SQLite 只读查询相关工具（同域合并，风格同 filesystem）。"""

from __future__ import annotations

from langchain_core.tools import tool

from db.manager import get_db_manager


def is_sql_check_failed(message: str) -> bool:
    return (
        "失败" in message
        or message.startswith("错误")
        or message.startswith("警告")
    )


def _fetch_rows(query: str, max_rows: int = 100_000) -> tuple[list[str], list[dict]]:
    return get_db_manager().fetch_query_rows(query, max_rows=max_rows)


@tool("sql_db_list_tables")
def sql_db_list_tables() -> str:
    """列出 SQLite 数据库中的所有表名及其描述信息。"""
    print("\033[33m→ sql_db_list_tables()\033[0m")
    try:
        tables_info = get_db_manager().get_tables_with_comments()
        lines = [f"数据库中共有 {len(tables_info)} 张表\n"]
        for i, table_info in enumerate(tables_info, start=1):
            table_name = table_info["table_name"]
            comment = (table_info.get("table_comment") or "").strip()
            description = comment if comment else "无描述信息"
            lines.append(f"表 {i}：{table_name}")
            lines.append(f"描述：{description}\n")
        out = "\n".join(lines)
    except Exception as e:
        out = f"获取数据库中的表名失败: {e}"
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out


@tool("sql_db_table_schema")
def sql_db_table_schema(table_names: list[str] | None = None) -> str:
    """获取表结构：表名、字段、类型、注释。table_names 为空则查全部表。"""
    print(f"\033[33m→ sql_db_table_schema({table_names!r})\033[0m")
    try:
        mgr = get_db_manager()
        names = table_names or []
        if not names:
            names = mgr.get_table_names()
        schema_info = mgr.get_table_schema(names)
        if not schema_info:
            out = "没有找到表结构信息"
        else:
            out = "\n\n".join(item["table_schema"] for item in schema_info)
    except Exception as e:
        out = f"获取指定表的结构信息失败: {e}"
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out


@tool("sql_db_query")
def sql_db_query(query: str) -> str:
    """执行只读 SQL 查询（SELECT / WITH），返回 JSON 结果。"""
    print(f"\033[33m→ sql_db_query({query[:80]!r}...)\033[0m")
    try:
        out = get_db_manager().execute_query(query)
    except Exception as e:
        out = f"执行 SQL 查询语句失败: {e}"
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out


@tool("sql_db_query_checker")
def sql_db_query_checker(query: str) -> str:
    """用 EXPLAIN 检查 SQL 查询语句是否有效。"""
    print(f"\033[33m→ sql_db_query_checker({query[:80]!r}...)\033[0m")
    try:
        out = get_db_manager().validate_query(query)
    except Exception as e:
        out = f"检查 SQL 查询语句失败: {e}"
    print(out)
    return out
