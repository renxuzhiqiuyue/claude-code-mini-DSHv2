"""MySQL 管理器（Text2SQL / 根因取数）。"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, List
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


def _sa() -> tuple[Any, Any, Any]:
    """惰性导入 sqlalchemy，避免进程早于依赖安装时把失败结果钉死。"""
    try:
        from sqlalchemy import create_engine, inspect, text
    except ImportError as e:
        raise RuntimeError(
            "未安装 sqlalchemy / pymysql，请在工程 venv 中执行: "
            "pip install sqlalchemy pymysql"
        ) from e
    return create_engine, inspect, text


class MySQLDatabaseManager:
    def __init__(self, connection_string: str, pool_size: int = 5, pool_recycle: int = 3600):
        create_engine, _, _ = _sa()
        self.engine = create_engine(
            connection_string,
            pool_size=pool_size,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,
        )

    def get_table_names(self) -> list[str]:
        _, inspect, _ = _sa()
        try:
            return inspect(self.engine).get_table_names()
        except Exception as e:
            logger.exception("获取表名失败: %s", e)
            raise ValueError(f"获取数据库中的表名失败: {e}") from e

    def get_tables_with_comments(self) -> List[dict]:
        _, _, text = _sa()
        try:
            query = text(
                """
                SELECT TABLE_NAME, TABLE_COMMENT
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
                """
            )
            with self.engine.connect() as conn:
                result = conn.execute(query)
                return [
                    {"table_name": row[0], "table_comment": row[1]}
                    for row in result.fetchall()
                ]
        except Exception as e:
            logger.exception("获取表注释失败: %s", e)
            raise ValueError(f"获取数据库中的表名和注释失败: {e}") from e

    def get_table_schema(self, table_names: list[str] | None = None) -> list[dict]:
        _, inspect, _ = _sa()
        try:
            inspector = inspect(self.engine)
            schema_info = []
            table_to_process = table_names if table_names else self.get_table_names()

            for table_name in table_to_process:
                columns = inspector.get_columns(table_name)
                pk_constraint = inspector.get_pk_constraint(table_name)
                primary_keys = pk_constraint["constrained_columns"] if pk_constraint else []
                foreign_keys = inspector.get_foreign_keys(table_name)

                table_schema = f"表名: {table_name}\n列信息：\n"
                for column in columns:
                    pk_indicator = "（主键）" if column["name"] in primary_keys else ""
                    comment = column.get("comment", "无注释")
                    table_schema += (
                        f"  - {column['name']}: {column['type']}{pk_indicator} "
                        f"[注释：{comment}]\n"
                    )

                if foreign_keys:
                    table_schema += "外键约束：\n"
                    for fk in foreign_keys:
                        local = ", ".join(fk.get("constrained_columns") or ())
                        remote_table = fk.get("referred_table") or "?"
                        remote_cols = ", ".join(fk.get("referred_columns") or ())
                        table_schema += f"  - {local} 引用 {remote_table} 的 {remote_cols}\n"

                schema_info.append({"table_name": table_name, "table_schema": table_schema})
            return schema_info
        except Exception as e:
            logger.exception("获取表结构失败: %s", e)
            raise ValueError(f"获取数据库中的表结构失败: {e}") from e

    def _assert_readonly_query(self, query: str) -> None:
        if not query or not query.strip():
            raise ValueError("查询语句不能为空")
        query_upper = query.upper()
        for keyword in ["DROP", "TRUNCATE", "ALTER", "CREATE", "INSERT", "UPDATE", "DELETE"]:
            if keyword in query_upper:
                raise ValueError(f"禁止执行包含关键词{keyword}的SQL语句")
        if not query_upper.strip().startswith(("SELECT", "WITH")):
            raise ValueError("查询语句必须以SELECT或WITH开头")

    def fetch_query_rows(
        self, query: str, max_rows: int = 100_000
    ) -> tuple[list[str], list[dict]]:
        _, _, text = _sa()
        self._assert_readonly_query(query)
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                column_names = list(result.keys())
                rows = result.fetchmany(max_rows + 1)
                if len(rows) > max_rows:
                    raise ValueError(f"查询结果超过上限 {max_rows} 行，请缩小 SQL 范围或增加聚合")
                result_data: list[dict] = []
                for row in rows:
                    row_data: dict = {}
                    for i, column in enumerate(column_names):
                        value = row[i]
                        try:
                            if value is not None:
                                json.dumps(value)
                            row_data[column] = value
                        except (TypeError, ValueError):
                            row_data[column] = str(value)
                    result_data.append(row_data)
                return column_names, result_data
        except ValueError:
            raise
        except Exception as e:
            logger.exception("执行SQL取数失败: %s", e)
            raise ValueError(f"执行SQL取数失败: {e}") from e

    def execute_query(self, query: str) -> str:
        _, _, text = _sa()
        self._assert_readonly_query(query)
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                column_names = result.keys()
                rows = result.fetchmany(size=100)
                if not rows:
                    return "查询结果为空"
                result_data = []
                for row in rows:
                    row_data = {}
                    for i, column in enumerate(column_names):
                        try:
                            if row[i] is not None:
                                json.dumps(row[i])
                            row_data[column] = row[i]
                        except (TypeError, ValueError):
                            row_data[column] = str(row[i])
                    result_data.append(row_data)
                return json.dumps(
                    {"row_count": len(result_data), "rows": result_data},
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.exception("执行SQL语句失败: %s", e)
            raise ValueError(f"执行SQL语句失败: {e}") from e

    def validate_query(self, query: str) -> str:
        _, _, text = _sa()
        if not query or not query.strip():
            return "错误：查询语句不能为空"
        query_stripped = query.strip()
        query_upper = query_stripped.upper()
        if not query_upper.startswith(("SELECT", "WITH")):
            return "警告：查询语句必须以SELECT或WITH开头"
        try:
            with self.engine.connect() as conn:
                conn.execute(text(f"EXPLAIN {query_stripped}"))
            return "sql查询语句EXPLAIN解析成功"
        except Exception as e:
            logger.exception("EXPLAIN 失败: %s", e)
            return f"sql查询语句EXPLAIN解析失败: {e}, 请检查查询语句是否正确"


def _mysql_url_from_env() -> str:
    # 兼容 MYSQL_* 与 DB_*
    user = os.getenv("DB_USER") or os.getenv("MYSQL_USER") or "root"
    password = os.getenv("DB_PASSWORD") or os.getenv("MYSQL_PASSWORD") or ""
    host = os.getenv("DB_HOST") or os.getenv("MYSQL_HOST") or "127.0.0.1"
    port = os.getenv("DB_PORT") or os.getenv("MYSQL_PORT") or "3306"
    database = os.getenv("DB_NAME") or os.getenv("MYSQL_DATABASE") or ""
    if not database:
        raise RuntimeError("未设置 DB_NAME / MYSQL_DATABASE")
    return (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}?charset=utf8mb4"
    )


@lru_cache(maxsize=1)
def get_mysql_manager() -> MySQLDatabaseManager:
    return MySQLDatabaseManager(_mysql_url_from_env())
