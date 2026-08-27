"""OS 级命令沙箱：包装 bash / python3。

后端（SANDBOX_BACKEND）：
  - auto（默认）：能用 bwrap 则 bwrap，否则 landlock-run
  - bwrap：将宿主机 OUTPUT_DIR bind 为 /workspace
  - landlock：内核限制可写范围；若存在 /workspace→OUTPUT_DIR 链接则 cwd=/workspace
  - off：仅 cwd=OUTPUT_DIR（软沙箱）

自带二进制：harness/bin/bwrap、harness/bin/landlock-run（优先于 PATH）。
"""

from harness.sandbox.backend import (
    bwrap_path,
    landlock_run_path,
    resolve_backend,
    sandbox_backend,
)
from harness.sandbox.constants import SANDBOX_CWD
from harness.sandbox.runner import run_bash, run_python, run_sandboxed, wrap_argv
from harness.sandbox.status import sandbox_status_line
from harness.sandbox.workspace import (
    ensure_workspace_link,
    last_bwrap_mount,
    prepare_sandbox_workdir,
)

__all__ = [
    "SANDBOX_CWD",
    "bwrap_path",
    "ensure_workspace_link",
    "landlock_run_path",
    "last_bwrap_mount",
    "prepare_sandbox_workdir",
    "resolve_backend",
    "run_bash",
    "run_python",
    "run_sandboxed",
    "sandbox_backend",
    "sandbox_status_line",
    "wrap_argv",
]
