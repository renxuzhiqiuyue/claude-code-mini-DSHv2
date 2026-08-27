"""工作区挂载：/workspace 符号链接、bwrap bind 点、最近一次挂载路径。"""

from __future__ import annotations

import os
from pathlib import Path

from harness import config as cfg
from harness.sandbox.backend import resolve_backend
from harness.sandbox.constants import BWRAP_FALLBACK_MOUNT, SANDBOX_CWD

# 最近一次 bwrap 实际挂载点（供 bash 路径归一化）
_last_bwrap_mount: str | None = None


def last_bwrap_mount() -> str | None:
    return _last_bwrap_mount


def set_last_bwrap_mount(mount: str | None) -> None:
    global _last_bwrap_mount
    _last_bwrap_mount = mount


def ensure_workspace_link(work: Path | None = None) -> bool:
    """尽量让 /workspace 指向 OUTPUT_DIR（landlock/off；bwrap 使用真实目录 bind）。"""
    try:
        if resolve_backend() == "bwrap":
            return False
    except RuntimeError:
        pass
    work = (work or cfg.OUTPUT_DIR).resolve()
    link = Path(SANDBOX_CWD)
    try:
        if link.is_dir() and not link.is_symlink():
            try:
                if not any(link.iterdir()):
                    link.rmdir()
            except OSError:
                pass
        if link.is_symlink():
            if link.resolve() == work:
                return True
            return False
        if link.exists():
            return False
        os.symlink(str(work), SANDBOX_CWD)
        return True
    except OSError:
        return False


def ensure_host_mount_dir(path: Path) -> bool:
    """确保 path 为可 bind 的真实目录（必要时去掉指向 OUTPUT_DIR 的 symlink 并 mkdir）。"""
    try:
        if path.is_symlink():
            path.unlink()
        elif path.is_file():
            return False
        if path.is_dir():
            return True
        path.mkdir(parents=True, exist_ok=True)
        return path.is_dir()
    except OSError:
        return False


def prepare_bwrap_mount(work: Path) -> str:
    """返回 bwrap --bind 的宿主机挂载点路径（须为真实目录）。"""
    primary = Path(SANDBOX_CWD)
    try:
        if primary.is_symlink():
            try:
                if primary.resolve() != work.resolve():
                    raise OSError("foreign symlink")
            except OSError:
                pass
            else:
                primary.unlink()
        if primary.is_dir() or ensure_host_mount_dir(primary):
            return SANDBOX_CWD
    except OSError:
        pass

    fallback = Path(BWRAP_FALLBACK_MOUNT)
    if ensure_host_mount_dir(fallback):
        print(
            f"  \033[33m[sandbox] bwrap 使用备用挂载点 {fallback}（/workspace 不可用）\033[0m"
        )
        return BWRAP_FALLBACK_MOUNT

    raise RuntimeError(
        "无法准备 bwrap 挂载目录：请确保 /workspace 或 "
        f"{BWRAP_FALLBACK_MOUNT} 可创建为真实目录，或改用 SANDBOX_BACKEND=landlock"
    )


def prepare_sandbox_workdir(work: Path | None = None) -> str:
    """解析沙箱内工作目录（bwrap 在运行命令前调用，便于路径归一化）。"""
    work = (work or cfg.OUTPUT_DIR).resolve()
    try:
        backend = resolve_backend()
    except RuntimeError:
        set_last_bwrap_mount(None)
        return str(work)
    if backend == "bwrap":
        mount = prepare_bwrap_mount(work)
        set_last_bwrap_mount(mount)
        return mount
    set_last_bwrap_mount(None)
    if backend == "landlock":
        ensure_workspace_link(work)
        link = Path(SANDBOX_CWD)
        try:
            if link.is_symlink() and link.resolve() == work.resolve():
                return SANDBOX_CWD
        except OSError:
            pass
    return str(work)
