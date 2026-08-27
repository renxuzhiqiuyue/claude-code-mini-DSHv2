"""landlock：内核限制可写范围；若 /workspace→OUTPUT_DIR 链接存在则 cwd=/workspace。"""

from __future__ import annotations

from pathlib import Path

from harness.sandbox.backend import landlock_run_path
from harness.sandbox.constants import SANDBOX_CWD
from harness.sandbox.workspace import ensure_workspace_link


def landlock_cwd(work: Path) -> str:
    ensure_workspace_link(work)
    link = Path(SANDBOX_CWD)
    try:
        if link.is_symlink() and link.resolve() == work.resolve():
            return SANDBOX_CWD
    except OSError:
        pass
    return str(work)


def wrap_landlock(inner: list[str], work: Path) -> list[str]:
    exe = landlock_run_path()
    assert exe
    # 勿把 /home 设为只读：OUTPUT_DIR 通常在其下，避免与 --rw 冲突
    ro = ["/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc", "/dev", "/proc", "/opt"]
    argv = [exe]
    for p in ro:
        if Path(p).exists():
            argv.extend(["--ro", p])
    # 解释器常经 /usr/bin/python3；再放行常见动态链接器路径已含在 /lib*
    argv.extend(["--rw", str(work), "--rw", "/tmp", "--", *inner])
    return argv
