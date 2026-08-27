"""沙箱进程执行入口。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from harness import config as cfg
from harness.sandbox.backend import resolve_backend
from harness.sandbox.bwrap import wrap_bwrap
from harness.sandbox.landlock import landlock_cwd, wrap_landlock
from harness.sandbox.workspace import set_last_bwrap_mount


def wrap_argv(inner: list[str], *, work: Path | None = None) -> tuple[list[str], str | None]:
    """返回 (argv, cwd)。cwd 在 bwrap 下为 None（已 --chdir）。"""
    work = (work or cfg.OUTPUT_DIR).resolve()
    backend = resolve_backend()
    if backend == "off":
        return list(inner), str(work)
    if backend == "bwrap":
        return wrap_bwrap(inner, work), None
    return wrap_landlock(inner, work), landlock_cwd(work)


def run_sandboxed(
    inner: list[str],
    *,
    work: Path | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    work = (work or cfg.OUTPUT_DIR).resolve()
    work.mkdir(parents=True, exist_ok=True)
    backend = resolve_backend()
    if backend != "bwrap":
        set_last_bwrap_mount(None)
    argv, cwd = wrap_argv(inner, work=work)
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_bash(command: str, *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run_sandboxed(["bash", "-c", command], timeout=timeout)


def run_python(*py_args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run_sandboxed(["python3", *py_args], timeout=timeout)
