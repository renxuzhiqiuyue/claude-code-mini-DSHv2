"""解析 SANDBOX_BACKEND：auto / bwrap / landlock / off。"""

from __future__ import annotations

import os
import shutil
import subprocess

from harness.sandbox.constants import BIN_DIR


def sandbox_backend() -> str:
    raw = (os.getenv("SANDBOX_BACKEND") or "auto").strip().lower()
    if raw in ("off", "0", "false", "no", "none"):
        return "off"
    if raw in ("bwrap", "bubblewrap"):
        return "bwrap"
    if raw in ("landlock", "ll", "landlock-run"):
        return "landlock"
    if raw in ("auto", "on", "1", "true", "yes", ""):
        return "auto"
    return raw


def find_tool(name: str) -> str | None:
    local = BIN_DIR / name
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which(name)


def bwrap_path() -> str | None:
    return find_tool("bwrap")


def landlock_run_path() -> str | None:
    return find_tool("landlock-run")


def bwrap_works() -> bool:
    exe = bwrap_path()
    if not exe:
        return False
    try:
        r = subprocess.run(
            [
                exe,
                "--ro-bind", "/", "/",
                "--bind", "/tmp", "/tmp",
                "--chdir", "/tmp",
                "--", "true",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def resolve_backend() -> str:
    """解析 auto → 实际后端。"""
    wanted = sandbox_backend()
    if wanted == "off":
        return "off"
    if wanted == "bwrap":
        if not bwrap_path():
            raise RuntimeError("SANDBOX_BACKEND=bwrap 但未找到 bwrap（可放 harness/bin/bwrap）")
        if not bwrap_works():
            raise RuntimeError(
                "bwrap 不可用（常见原因：禁止创建 user namespace）。"
                "请改用 SANDBOX_BACKEND=landlock 或 auto"
            )
        return "bwrap"
    if wanted == "landlock":
        if not landlock_run_path():
            raise RuntimeError(
                "SANDBOX_BACKEND=landlock 但未找到 landlock-run（见 harness/bin/landlock-run）"
            )
        return "landlock"
    # auto
    if bwrap_path() and bwrap_works():
        return "bwrap"
    if landlock_run_path():
        return "landlock"
    raise RuntimeError(
        "无可用沙箱后端：请安装 bubblewrap，或确保 harness/bin/landlock-run 存在；"
        "调试可设 SANDBOX_BACKEND=off"
    )
