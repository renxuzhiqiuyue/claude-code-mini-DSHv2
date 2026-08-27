"""`.memory/` 路径（可在测试中改写本模块属性）。"""

from pathlib import Path

from harness.config import MEMORY_DIR

MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
STATE_FILE = MEMORY_DIR / ".consolidate_state.json"
