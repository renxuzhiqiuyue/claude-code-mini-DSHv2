"""数据库连接系统。

Skill（如 read_sql_data）与后续 SQL 工具从此处取连接。
凭证优先读环境变量 / `.env`：DB_HOST、DB_PORT、DB_USER、DB_PASSWORD、DB_NAME。
"""

from __future__ import annotations

import os
from typing import Any

# 可选依赖：未安装时给出明确提示，不阻断其它模块导入
try:
    import pymysql
except ImportError:  # pragma: no cover
    pymysql = None  # type: ignore

try:
    from sqlalchemy import create_engine
    from sqlalchemy.engine import Engine
except ImportError:  # pragma: no cover
    create_engine = None  # type: ignore
    Engine = Any  # type: ignore


def _db_settings() -> dict[str, Any]:
    return {
        "host": os.environ.get("DB_HOST", "127.0.0.1"),
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", ""),
        "charset": os.environ.get("DB_CHARSET", "utf8mb4"),
    }


def get_connection():
    """返回 pymysql 连接（调用方负责 close）。"""
    if pymysql is None:
        raise RuntimeError("未安装 pymysql，请 pip install pymysql")
    cfg = _db_settings()
    if not cfg["database"]:
        raise RuntimeError("请设置环境变量 DB_NAME")
    return pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset=cfg["charset"],
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_engine() -> Engine:
    """返回 SQLAlchemy Engine（可选）。"""
    if create_engine is None:
        raise RuntimeError("未安装 sqlalchemy，请 pip install sqlalchemy")
    cfg = _db_settings()
    if not cfg["database"]:
        raise RuntimeError("请设置环境变量 DB_NAME")
    url = (
        f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset={cfg['charset']}"
    )
    return create_engine(url, pool_pre_ping=True)
