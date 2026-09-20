"""SQLite 管理器（Text2SQL / 根因取数）。"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, List

from db.connection import sqlite_url

logger = logging.getLogger(__name__)

TABLE_COMMENTS = {
    "iss_ins_dim": "发卡机构维度表",
    "usr_dim": "用户维度表",
    "mchnt_dim": "商户维度表",
    "card_info": "卡号信息表",
    "yjhx_trans_detail": "以旧换新交易明细表",
}

COLUMN_COMMENTS = {
    ("iss_ins_dim", "iss_ins_id_cd"): "发卡机构代码",
    ("iss_ins_dim", "iss_ins_nm"): "发卡机构中文名称",
    ("usr_dim", "usr_id"): "用户 ID",
    ("usr_dim", "usr_city_nm"): "城市",
    ("usr_dim", "branch_org_cd"): "分公司代码",
    ("usr_dim", "branch_org_nm"): "分公司名称",
    ("usr_dim", "age"): "年龄",
    ("usr_dim", "sex"): "性别",
    ("usr_dim", "trans_level"): "交易水平",
    ("mchnt_dim", "mchnt_cd"): "商编",
    ("mchnt_dim", "mchnt_nm"): "商户名称",
    ("mchnt_dim", "mchnt_city_nm"): "所属城市",
    ("mchnt_dim", "acq_ins_id_cd"): "收单机构代码",
    ("mchnt_dim", "acq_ins_nm"): "收单机构名称",
    ("card_info", "card_no"): "卡号",
    ("card_info", "usr_id"): "用户 ID",
    ("card_info", "iss_ins_id_cd"): "发卡机构代码",
    ("card_info", "card_attr"): "卡性质",
    ("card_info", "card_brand"): "卡品牌",
    ("yjhx_trans_detail", "issuer_tp"): "发券方",
    ("yjhx_trans_detail", "mchnt_cd"): "商编",
    ("yjhx_trans_detail", "usr_id"): "用户 ID",
    ("yjhx_trans_detail", "card_no"): "卡号",
    ("yjhx_trans_detail", "iss_ins_id_cd"): "发卡机构代码",
    ("yjhx_trans_detail", "prod_nm"): "商品名称",
    ("yjhx_trans_detail", "prod_tp"): "商品大类",
    ("yjhx_trans_detail", "eng_grade"): "能级分类",
    ("yjhx_trans_detail", "brand_nm"): "品牌名称",
    ("yjhx_trans_detail", "act_id"): "活动 ID",
    ("yjhx_trans_detail", "act_nm"): "活动名称",
    ("yjhx_trans_detail", "rec_city_nm"): "收货城市",
    ("yjhx_trans_detail", "rec_dt"): "收货日期",
    ("yjhx_trans_detail", "trans_amt"): "交易金额",
    ("yjhx_trans_detail", "discount_amt"): "补贴金额",
    ("yjhx_trans_detail", "income_amt"): "收入金额",
    ("yjhx_trans_detail", "trans_dt"): "交易日期（月报主时间字段，YYYY-MM-DD）",
    ("yjhx_trans_detail", "trans_tm"): "交易时间",
    ("yjhx_trans_detail", "pay_tp"): "支付方式",
    ("yjhx_trans_detail", "is_payment"): "是否分期",
    ("yjhx_trans_detail", "is_online"): "是否线上",
}


def _sa() -> tuple[Any, Any, Any, Any]:
    """惰性导入 sqlalchemy，避免进程早于依赖安装时把失败结果钉死。"""
    try:
        from sqlalchemy import create_engine, inspect, text
        from sqlalchemy.pool import StaticPool
    except ImportError as e:
        raise RuntimeError(
            "未安装 sqlalchemy，请在工程 venv 中执行: pip install sqlalchemy"
        ) from e
    return create_engine, inspect, text, StaticPool


class DatabaseManager:
    def __init__(self, connection_string: str | None = None):
        create_engine, _, _, StaticPool = _sa()
        url = connection_string or sqlite_url()
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "uri": True},
            poolclass=StaticPool,
        )

    def get_table_names(self) -> list[str]:
        _, inspect, _, _ = _sa()
        try:
            names = inspect(self.engine).get_table_names()
            return [n for n in names if not n.startswith("sqlite_")]
        except Exception as e:
            logger.exception("获取表名失败: %s", e)
            raise ValueError(f"获取数据库中的表名失败: {e}") from e

    def get_tables_with_comments(self) -> List[dict]:
        try:
            return [
                {
                    "table_name": name,
                    "table_comment": TABLE_COMMENTS.get(name, ""),
                }
                for name in self.get_table_names()
            ]
        except Exception as e:
            logger.exception("获取表注释失败: %s", e)
            raise ValueError(f"获取数据库中的表名和注释失败: {e}") from e

    def get_table_schema(self, table_names: list[str] | None = None) -> list[dict]:
        _, inspect, _, _ = _sa()
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
                    comment = (
                        COLUMN_COMMENTS.get((table_name, column["name"]))
                        or column.get("comment")
                        or "无注释"
                    )
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
        _, _, text, _ = _sa()
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
        _, _, text, _ = _sa()
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
        _, _, text, _ = _sa()
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


# 兼容旧名
MySQLDatabaseManager = DatabaseManager


@lru_cache(maxsize=1)
def get_db_manager() -> DatabaseManager:
    return DatabaseManager()


get_mysql_manager = get_db_manager
