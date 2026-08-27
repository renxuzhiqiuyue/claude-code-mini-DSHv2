"""进程内会话状态。"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from harness.memory.constants import SHORT_TERM_MAX

short_term: deque[dict] = deque(maxlen=SHORT_TERM_MAX)
current_session_dir: Path | None = None
current_session: Path | None = None  # .../session.jsonl
session_started_at: str = ""
session_meta: dict = {}
solver_session: Path | None = None
solver_session_meta: dict = {}
# 每个 jsonl 文件最近写入的毫秒时间戳，保证同文件内 ts 单调递增
last_event_ts_ms: dict[str, int] = {}
