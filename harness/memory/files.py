"""MEMORY.md 文件与 Consolidation 状态。"""

from __future__ import annotations

import json
from datetime import datetime

from harness.memory import paths
from harness.memory.constants import MEMORY_TEMPLATE


def ensure_memory_files() -> None:
    paths.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not paths.MEMORY_FILE.exists():
        paths.MEMORY_FILE.write_text(MEMORY_TEMPLATE, encoding="utf-8")


def parse_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    meta: dict = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, parts[2].strip()


def load_state() -> dict:
    if not paths.STATE_FILE.exists():
        return {"consolidated": []}
    try:
        return json.loads(paths.STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"consolidated": []}


def save_state(state: dict) -> None:
    paths.STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_consolidated(session_name: str, *, updated: bool) -> None:
    state = load_state()
    done = set(state.get("consolidated") or [])
    done.add(session_name)
    state["consolidated"] = sorted(done)
    if updated:
        state["last_update"] = datetime.now().isoformat(timespec="seconds")
    save_state(state)


def is_session_consolidated(session_name: str) -> bool:
    state = load_state()
    return session_name in set(state.get("consolidated") or [])
