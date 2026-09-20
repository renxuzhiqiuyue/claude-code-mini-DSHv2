"""数据库连接：只读 SQLite（db/data/deepReport.sqlite）。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

try:
    from sqlalchemy import create_engine
    from sqlalchemy.engine import Engine
    from sqlalchemy.pool import StaticPool
except ImportError:  # pragma: no cover
    create_engine = None  # type: ignore
    Engine = Any  # type: ignore
    StaticPool = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = ROOT / "db" / "data" / "deepReport.sqlite"


def sqlite_path() -> Path:
    raw = (os.environ.get("DB_SQLITE_PATH") or "").strip()
    p = Path(raw).expanduser() if raw else DEFAULT_SQLITE
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def _assert_sqlite_file(path: Path) -> Path:
    if not path.is_file():
        raise RuntimeError(f"SQLite 文件不存在: {path}")
    return path


def sqlite_url(path: Path | None = None) -> str:
    """SQLAlchemy 只读 URI。"""
    db = _assert_sqlite_file(path or sqlite_path())
    return f"sqlite+pysqlite:///file:{db.as_posix()}?mode=ro&uri=true"


def get_connection() -> sqlite3.Connection:
    """返回 sqlite3 只读连接（调用方负责 close）。"""
    db = _assert_sqlite_file(sqlite_path())
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_engine() -> Engine:
    """返回 SQLAlchemy Engine（只读）。"""
    if create_engine is None or StaticPool is None:
        raise RuntimeError("未安装 sqlalchemy，请 pip install sqlalchemy")
    return create_engine(
        sqlite_url(),
        connect_args={"check_same_thread": False, "uri": True},
        poolclass=StaticPool,
    )
