"""全工具可用性冒烟：直接 invoke 各 @tool（不经 Agent 循环）。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env", override=True)

from harness.config import set_output_dir, ensure_runtime_dirs

set_output_dir(os.getenv("OUTPUT_DIR") or ".output")
ensure_runtime_dirs()


def _ok(name: str, detail: str = "") -> None:
    print(f"  [OK] {name}" + (f" — {detail}" if detail else ""))


def _fail(name: str, err: str) -> None:
    print(f"  [FAIL] {name} — {err}")


def _invoke(tool, payload: dict):
    return tool.invoke(payload)


def main() -> int:
    from tools import TOOLS

    failed = 0
    print(f"注册工具数: {len(TOOLS)}")
    names = [t.name for t in TOOLS]
    print("  " + ", ".join(names))

    # —— filesystem / bash ——
    try:
        from tools.bash import bash
        from tools.filesystem import edit_file, read_file, write_file

        out = _invoke(write_file, {"path": "_smoke/hello.txt", "content": "hello-smoke\n"})
        assert "已写入" in out
        out = _invoke(read_file, {"path": "_smoke/hello.txt"})
        assert "hello-smoke" in out
        out = _invoke(edit_file, {"path": "_smoke/hello.txt", "old_text": "hello", "new_text": "hi"})
        assert "已编辑" in out
        out = _invoke(bash, {"command": "python3 -c \"print(1+1)\""})
        assert "2" in out
        _ok("bash / read_file / write_file / edit_file")
    except Exception as e:
        failed += 1
        _fail("filesystem+bash", str(e))

    # —— todo / skill / task ——
    try:
        from tools.todo_write import todo_write
        from tools.load_skill import load_skill

        out = _invoke(
            todo_write,
            {"todos": [{"content": "smoke", "status": "completed"}]},
        )
        assert "待办" in out or "1" in out
        out = _invoke(load_skill, {"name": "read-sql-data"})
        assert "SKILL" in out or "MySQL" in out or "取数" in out
        _ok("todo_write / load_skill")
    except Exception as e:
        failed += 1
        _fail("todo/load_skill", str(e))

    try:
        from tools.task import task

        # 子 Agent 需 API；仅检查工具可调用签名（短任务可能耗时），这里只验证 tool 对象
        assert task.name == "task"
        _ok("task（已注册，跳过真实子 Agent 调用）")
    except Exception as e:
        failed += 1
        _fail("task", str(e))

    # —— text2sql ——
    try:
        from tools.text2sql import (
            sql_db_list_tables,
            sql_db_query,
            sql_db_query_checker,
            sql_db_table_schema,
        )
        from db import manager as dbm

        dbm.get_mysql_manager.cache_clear()

        out = _invoke(sql_db_list_tables, {})
        if "失败" in out:
            raise RuntimeError(out[:200])
        out = _invoke(sql_db_query_checker, {"query": "SELECT 1 AS n"})
        if "成功" not in out:
            raise RuntimeError(out[:200])
        out = _invoke(sql_db_query, {"query": "SELECT 1 AS n"})
        if "失败" in out or "错误" in out[:10]:
            raise RuntimeError(out[:200])
        out = _invoke(sql_db_table_schema, {"table_names": ["yjhx_trans_detail"]})
        if "失败" in out:
            raise RuntimeError(out[:200])
        _ok("sql_db_*")
    except Exception as e:
        failed += 1
        _fail("text2sql", str(e))

    # —— root_cause（用内存小样，不强制真库长表）——
    try:
        from tools.root_cause import build_root_cause_tree
        from tools import root_cause_utils as rc

        rows = [
            {"period": "当期", "prod_tp": "A", "city": "沪", "amt": "100"},
            {"period": "基期", "prod_tp": "A", "city": "沪", "amt": "80"},
            {"period": "当期", "prod_tp": "B", "city": "沪", "amt": "50"},
            {"period": "基期", "prod_tp": "B", "city": "沪", "amt": "40"},
            {"period": "当期", "prod_tp": "A", "city": "京", "amt": "30"},
            {"period": "基期", "prod_tp": "A", "city": "京", "amt": "20"},
            {"period": "当期", "prod_tp": "B", "city": "京", "amt": "10"},
            {"period": "基期", "prod_tp": "B", "city": "京", "amt": "5"},
        ]
        out = _invoke(
            build_root_cause_tree,
            {
                "metric": "amt",
                "dimensions": "prod_tp,city",
                "data": rows,
                "output_format": "json",
            },
        )
        data = json.loads(out)
        assert data.get("success") is True or "drill_path" in data or "tree" in data
        # fetch 依赖真库；至少校验工具可 import + checker 路径
        from tools.root_cause import fetch_period_data

        assert fetch_period_data.name == "fetch_period_data"
        _ok("build_root_cause_tree（样例数据）+ fetch_period_data 已注册")
    except Exception as e:
        failed += 1
        _fail("root_cause", str(e))

    # —— tavily ——
    try:
        from tools.tavily_search import tavily_search

        key = (os.getenv("TAVILY_API_KEY") or "").strip()
        if not key:
            out = _invoke(tavily_search, {"query": "test", "max_results": 1})
            if "未设置 TAVILY_API_KEY" in out or "未安装 tavily" in out:
                _ok("tavily_search（已注册；缺依赖或未配置 KEY，调用返回明确错误）")
            else:
                raise RuntimeError(f"预期配置错误提示，实际: {out[:120]}")
        else:
            out = _invoke(tavily_search, {"query": "以旧换新", "max_results": 1})
            if "失败" in out[:20]:
                raise RuntimeError(out[:200])
            _ok("tavily_search")
    except Exception as e:
        failed += 1
        _fail("tavily_search", str(e))

    print()
    if failed:
        print(f"失败 {failed} 项")
        return 1
    print("全部检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
