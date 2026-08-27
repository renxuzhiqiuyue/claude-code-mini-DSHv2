"""分层记忆（程序确定性时机读写，不经 OUTPUT_DIR）。

会话布局（每会话一个文件夹）：
  .memory/
    MEMORY.md
    session_<slug>/
      session.jsonl          # Planner 轨迹
      solver/
        session_<slug>.jsonl # 每次 Solver 子轨迹

无旧版 .json / 平铺 .jsonl 兼容。
"""

from harness.memory.consolidate import compress_session, consolidate_session, session_needs_compress
from harness.memory.constants import (
    MEMORY_TEMPLATE,
    SESSION_COMPRESS_MARKER,
    SESSION_COMPRESS_USER_TEXT,
    SESSION_JSONL,
    SHORT_TERM_MAX,
)
from harness.memory.files import ensure_memory_files, is_session_consolidated
from harness.memory.jsonl import (
    append_jsonl_event,
    iter_session_dirs,
    load_session_view,
    read_jsonl_events,
)
from harness.memory.layers import load_memory_layer, memory_core_for_prompt
from . import paths, runtime
from .paths import MEMORY_DIR, MEMORY_FILE, STATE_FILE
from harness.memory.query import (
    get_session_events,
    list_planner_sessions,
    list_session_subagents,
    resolve_session_jsonl,
)
from harness.memory.session import (
    append_parent_event,
    create_new_session,
    current_session_dir_name,
    current_session_log_text,
    current_session_name,
    prompt_choose_session,
    record_turn,
    resume_session,
    session_started,
    start_session,
    sync_session_messages,
)
from harness.memory.solver import (
    current_solver_session_name,
    end_solver_session,
    start_solver_session,
    sync_solver_session_messages,
)

__all__ = [
    "MEMORY_DIR",
    "MEMORY_FILE",
    "MEMORY_TEMPLATE",
    "SESSION_COMPRESS_MARKER",
    "SESSION_COMPRESS_USER_TEXT",
    "SESSION_JSONL",
    "SHORT_TERM_MAX",
    "STATE_FILE",
    "append_jsonl_event",
    "append_parent_event",
    "compress_session",
    "consolidate_session",
    "create_new_session",
    "current_session_dir_name",
    "current_session_log_text",
    "current_session_name",
    "current_solver_session_name",
    "end_solver_session",
    "ensure_memory_files",
    "get_session_events",
    "is_session_consolidated",
    "iter_session_dirs",
    "list_planner_sessions",
    "list_session_subagents",
    "load_memory_layer",
    "load_session_view",
    "memory_core_for_prompt",
    "paths",
    "prompt_choose_session",
    "read_jsonl_events",
    "record_turn",
    "resolve_session_jsonl",
    "resume_session",
    "runtime",
    "session_needs_compress",
    "session_started",
    "start_session",
    "start_solver_session",
    "sync_session_messages",
    "sync_solver_session_messages",
]
