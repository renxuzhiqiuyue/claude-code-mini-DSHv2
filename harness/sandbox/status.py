"""沙箱状态一行摘要（启动日志 / bash 工具前缀）。"""

from __future__ import annotations

from pathlib import Path

from harness import config as cfg
from harness.sandbox.backend import resolve_backend
from harness.sandbox.constants import SANDBOX_CWD
from harness.sandbox.workspace import last_bwrap_mount


def sandbox_status_line() -> str:
    try:
        backend = resolve_backend()
    except Exception as e:
        return f"沙箱：不可用（{e}）"
    if backend == "off":
        return f"沙箱：off（cwd={cfg.OUTPUT_DIR}）"
    if backend == "bwrap":
        mount = last_bwrap_mount() or SANDBOX_CWD
        return f"沙箱：bwrap → {cfg.OUTPUT_DIR} ⇔ {mount}"
    linked = False
    try:
        linked = Path(SANDBOX_CWD).is_symlink() and Path(SANDBOX_CWD).resolve() == cfg.OUTPUT_DIR.resolve()
    except OSError:
        pass
    cwd_hint = SANDBOX_CWD if linked else str(cfg.OUTPUT_DIR)
    return f"沙箱：landlock → 可写 {cfg.OUTPUT_DIR}；cwd={cwd_hint}"
