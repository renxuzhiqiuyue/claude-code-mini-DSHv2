"""权限规则（纯逻辑，无 LangChain 依赖）。

CLI：TTY 下对破坏性 bash `input()` 询问。
Web：通过 ContextVar + 线程本地注入 approver，阻塞等待前端决策（HITL）。
"""

from __future__ import annotations

import os
import re
import sys
import threading
from contextvars import ContextVar
from typing import Callable

from harness.config import DENY_LIST, DESTRUCTIVE, resolve_output_path

# (tool_name, args, reason) -> True 允许 / False 拒绝
Approver = Callable[[str, dict, str], bool]
_approver_var: ContextVar[Approver | None] = ContextVar("mini_cc_approver", default=None)
_tls = threading.local()

# bash 内嵌 Python 删除：os.remove / unlink / rmtree 等也需 HITL
_PY_DELETE_RE = re.compile(
    r"""
    os\s*\.\s*remove\s*\(
    | os\s*\.\s*unlink\s*\(
    | pathlib\s*\.\s*Path\s*\([^)]*\)\s*\.\s*unlink\s*\(
    | Path\s*\([^)]*\)\s*\.\s*unlink\s*\(
    | shutil\s*\.\s*rmtree\s*\(
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _needs_destructive_ask(command: str) -> bool:
    if any(token in command for token in DESTRUCTIVE):
        return True
    return _PY_DELETE_RE.search(command) is not None


def bind_approver(approver: Approver):
    """绑定当前执行上下文的 HITL 审批函数，返回 token 供 reset。"""
    _tls.approver = approver
    return _approver_var.set(approver)


def reset_approver(token) -> None:
    _approver_var.reset(token)
    _tls.approver = None


def _current_approver() -> Approver | None:
    return _approver_var.get() or getattr(_tls, "approver", None)


def _interactive() -> bool:
    if os.getenv("MINI_CC_NONINTERACTIVE", "").strip() in ("1", "true", "yes"):
        return False
    return sys.stdin.isatty()


def _ask_destructive(tool_name: str, args: dict, command: str) -> str | None:
    """破坏性操作询问。返回拒绝原因或 None（允许）。"""
    reason = "可能具有破坏性的命令"
    print(f"\n\033[33m[权限] {reason}\033[0m\n  {command}")

    approver = _current_approver()
    if approver is not None:
        try:
            allowed = bool(approver(tool_name, args, reason))
        except Exception as e:
            return f"权限拒绝：审批失败（{e}）"
        if not allowed:
            return "权限拒绝：用户未批准"
        return None

    if not _interactive():
        return "权限拒绝：非交互环境且未挂载 HITL 审批"

    choice = input("  是否允许？[y/N] ").strip().lower()
    if choice not in ("y", "yes", "是"):
        return "权限拒绝：用户未批准"
    return None


def check_tool_permission(tool_name: str, args: dict) -> str | None:
    """返回 None 表示允许；返回字符串表示拒绝原因。"""
    if tool_name == "bash":
        command = args.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                return f"权限拒绝：命令包含禁止模式「{pattern}」"
        if _needs_destructive_ask(command):
            return _ask_destructive(tool_name, args, command)

    if tool_name in ("write_file", "edit_file", "read_file"):
        path = args.get("path", "")
        try:
            resolve_output_path(path)
        except Exception as e:
            return f"权限拒绝：路径不在 OUTPUT_DIR 内（{e}）"

    return None
