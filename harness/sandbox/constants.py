"""沙箱路径常量。"""

from pathlib import Path

SANDBOX_CWD = "/workspace"
# bwrap 在 --ro-bind / / 后无法在根目录 mkdir；挂载点须为宿主机上已存在的真实目录（非 symlink）
BWRAP_FALLBACK_MOUNT = "/mnt/claude-code-mini-workspace"
# 自带二进制：harness/bin/bwrap、harness/bin/landlock-run（优先于 PATH）
BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
