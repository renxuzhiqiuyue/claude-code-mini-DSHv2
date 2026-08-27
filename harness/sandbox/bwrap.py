"""bubblewrap：将宿主机 OUTPUT_DIR bind 为 /workspace（或备用挂载点）。"""

from __future__ import annotations

from pathlib import Path

from harness.sandbox.backend import bwrap_path
from harness.sandbox.workspace import prepare_bwrap_mount, set_last_bwrap_mount


def wrap_bwrap(inner: list[str], work: Path) -> list[str]:
    exe = bwrap_path()
    assert exe
    host = str(work)
    mount = prepare_bwrap_mount(work)
    set_last_bwrap_mount(mount)
    return [
        exe,
        "--die-with-parent",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--bind", host, mount,
        "--chdir", mount,
        "--",
        *inner,
    ]
