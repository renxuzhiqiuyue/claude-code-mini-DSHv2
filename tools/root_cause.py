"""root_cause：当期/基期根因下钻（fetch + build）。"""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.tools import tool

from db.manager import get_mysql_manager
from tools import root_cause_utils as rc
from tools.text2sql import is_sql_check_failed


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _fetch_rows_from_sql(sql: str) -> tuple[list[str], list[dict]] | str:
    mgr = get_mysql_manager()
    check_result = mgr.validate_query(sql)
    if is_sql_check_failed(check_result):
        return json.dumps(
            {"valid": False, "errors": [check_result]},
            ensure_ascii=False,
            indent=2,
        )
    try:
        columns, raw_rows = mgr.fetch_query_rows(sql)
    except ValueError as e:
        return json.dumps(
            {"valid": False, "errors": [str(e)]},
            ensure_ascii=False,
            indent=2,
        )
    if not raw_rows:
        return json.dumps(
            {"valid": False, "errors": ["MySQL 查询结果为空"]},
            ensure_ascii=False,
            indent=2,
        )
    return columns, raw_rows


@tool("fetch_period_data")
def fetch_period_data(
    sql: str,
    metric: str,
    dimensions: str,
    period_col: str = "period",
    current_label: str = "当期",
    base_label: str = "基期",
) -> str:
    """从 MySQL 取当期/基期长表（一个指标 + 多维度），校验后返回 data 或 cache_id。"""
    print(f"\033[33m→ fetch_period_data(metric={metric!r})\033[0m")
    try:
        dimension_list = _split_list(dimensions)
        fetched = _fetch_rows_from_sql(sql)
        if isinstance(fetched, str):
            return fetched
        columns, raw_rows = fetched
        rows = rc.normalize_rows(raw_rows)
        validation = rc.validate_rows(
            columns,
            rows,
            period_col,
            metric,
            dimension_list,
            current_label,
            base_label,
        )
        payload: dict[str, Any] = {
            "valid": validation["valid"],
            "errors": validation.get("errors", []),
            "source": "mysql",
            "row_count": validation["row_count"],
            "columns": validation["columns"],
            "period_values": validation.get("period_values", []),
            "period_col": period_col,
            "metric": metric,
            "dimensions": dimension_list,
            "current_label": current_label,
            "base_label": base_label,
            "data": rows,
        }
        if validation["valid"] and len(rows) > rc.INLINE_ROW_LIMIT:
            cache_id = rc.save_dataset(payload)
            summary = {
                "valid": True,
                "source": "mysql",
                "row_count": len(rows),
                "columns": columns,
                "period_values": validation.get("period_values", []),
                "period_col": period_col,
                "metric": metric,
                "dimensions": dimension_list,
                "current_label": current_label,
                "base_label": base_label,
                "cache_id": cache_id,
                "message": (
                    f"数据已缓存（{len(rows)} 行），请用 cache_id 调用 build_root_cause_tree"
                ),
            }
            out = json.dumps(summary, ensure_ascii=False, indent=2)
        else:
            out = json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as e:
        out = json.dumps({"valid": False, "errors": [str(e)]}, ensure_ascii=False, indent=2)
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out


@tool("build_root_cause_tree")
def build_root_cause_tree(
    metric: str,
    dimensions: str,
    period_col: str = "period",
    data: list[dict[str, Any]] | None = None,
    cache_id: str | None = None,
    current_label: str = "当期",
    base_label: str = "基期",
    cum_threshold: float = 0.6,
    output_format: Literal["json", "markdown", "both"] = "both",
) -> str:
    """基于 fetch_period_data 长表做固定 2 层根因下钻，输出 JSON / Markdown。"""
    print(f"\033[33m→ build_root_cause_tree(metric={metric!r})\033[0m")
    try:
        if not data and not cache_id:
            return json.dumps(
                {"success": False, "errors": ["data 与 cache_id 必须提供其一"]},
                ensure_ascii=False,
                indent=2,
            )
        if cache_id:
            payload = rc.load_dataset(cache_id)
            rows = rc.normalize_rows(payload.get("data", []))
        else:
            rows = rc.normalize_rows(data or [])
        if not rows:
            return json.dumps(
                {"success": False, "errors": ["数据为空，请先调用 fetch_period_data"]},
                ensure_ascii=False,
                indent=2,
            )
        dimension_list = _split_list(dimensions)
        result = rc.build_root_cause_drill(
            rows,
            metric,
            dimension_list,
            period_col,
            current_label,
            base_label,
            cum_threshold,
        )
        if output_format == "markdown":
            out = rc.format_tree_report(result)
        elif output_format == "json":
            out = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            out = json.dumps(
                {"result": result, "markdown": rc.format_tree_report(result)},
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        out = json.dumps({"success": False, "errors": [str(e)]}, ensure_ascii=False, indent=2)
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out
