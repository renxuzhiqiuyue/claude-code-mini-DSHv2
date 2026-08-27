"""OS 级命令沙箱：包装 bash / python3。

后端（SANDBOX_BACKEND）：
  - auto（默认）：能用 bwrap 则 bwrap，否则 landlock-run
  - bwrap：将宿主机 OUTPUT_DIR bind 为 /workspace
  - landlock：内核限制可写范围；若存在 /workspace→OUTPUT_DIR 链接则 cwd=/workspace
  - off：仅 cwd=OUTPUT_DIR（软沙箱）

自带二进制：harness/bin/bwrap、harness/bin/landlock-run（优先于 PATH）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from harness import config as cfg

SANDBOX_CWD = "/workspace"
_BIN_DIR = Path(__file__).resolve().parent / "bin"


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


def _find_tool(name: str) -> str | None:
    local = _BIN_DIR / name
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which(name)


def bwrap_path() -> str | None:
    return _find_tool("bwrap")


def landlock_run_path() -> str | None:
    return _find_tool("landlock-run")


def _bwrap_works() -> bool:
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
        if not _bwrap_works():
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
    if bwrap_path() and _bwrap_works():
        return "bwrap"
    if landlock_run_path():
        return "landlock"
    raise RuntimeError(
        "无可用沙箱后端：请安装 bubblewrap，或确保 harness/bin/landlock-run 存在；"
        "调试可设 SANDBOX_BACKEND=off"
    )


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


# bwrap 在 --ro-bind / / 后无法在根目录 mkdir；挂载点须为宿主机上已存在的真实目录（非 symlink）
_BWRAP_FALLBACK_MOUNT = "/mnt/claude-code-mini-workspace"


def _ensure_host_mount_dir(path: Path) -> bool:
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


def _prepare_bwrap_mount(work: Path) -> str:
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
        if primary.is_dir() or _ensure_host_mount_dir(primary):
            return SANDBOX_CWD
    except OSError:
        pass

    fallback = Path(_BWRAP_FALLBACK_MOUNT)
    if _ensure_host_mount_dir(fallback):
        print(
            f"  \033[33m[sandbox] bwrap 使用备用挂载点 {fallback}（/workspace 不可用）\033[0m"
        )
        return _BWRAP_FALLBACK_MOUNT

    raise RuntimeError(
        "无法准备 bwrap 挂载目录：请确保 /workspace 或 "
        f"{_BWRAP_FALLBACK_MOUNT} 可创建为真实目录，或改用 SANDBOX_BACKEND=landlock"
    )


def prepare_sandbox_workdir(work: Path | None = None) -> str:
    """解析沙箱内工作目录（bwrap 在运行命令前调用，便于路径归一化）。"""
    global _last_bwrap_mount
    work = (work or cfg.OUTPUT_DIR).resolve()
    try:
        backend = resolve_backend()
    except RuntimeError:
        _last_bwrap_mount = None
        return str(work)
    if backend == "bwrap":
        mount = _prepare_bwrap_mount(work)
        _last_bwrap_mount = mount
        return mount
    _last_bwrap_mount = None
    if backend == "landlock":
        ensure_workspace_link(work)
        link = Path(SANDBOX_CWD)
        try:
            if link.is_symlink() and link.resolve() == work.resolve():
                return SANDBOX_CWD
        except OSError:
            pass
    return str(work)


def last_bwrap_mount() -> str | None:
    return _last_bwrap_mount


# 最近一次 bwrap 实际挂载点（供 bash 路径归一化）
_last_bwrap_mount: str | None = None


def wrap_argv(inner: list[str], *, work: Path | None = None) -> tuple[list[str], str | None]:
    """返回 (argv, cwd)。cwd 在 bwrap 下为 None（已 --chdir）。"""
    work = (work or cfg.OUTPUT_DIR).resolve()
    backend = resolve_backend()
    if backend == "off":
        return list(inner), str(work)
    if backend == "bwrap":
        return _wrap_bwrap(inner, work), None
    return _wrap_landlock(inner, work), _landlock_cwd(work)


def _wrap_bwrap(inner: list[str], work: Path) -> list[str]:
    global _last_bwrap_mount
    exe = bwrap_path()
    assert exe
    host = str(work)
    mount = _prepare_bwrap_mount(work)
    _last_bwrap_mount = mount
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


def _landlock_cwd(work: Path) -> str:
    ensure_workspace_link(work)
    link = Path(SANDBOX_CWD)
    try:
        if link.is_symlink() and link.resolve() == work.resolve():
            return SANDBOX_CWD
    except OSError:
        pass
    return str(work)


def _wrap_landlock(inner: list[str], work: Path) -> list[str]:
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


def run_sandboxed(
    inner: list[str],
    *,
    work: Path | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    global _last_bwrap_mount
    work = (work or cfg.OUTPUT_DIR).resolve()
    work.mkdir(parents=True, exist_ok=True)
    backend = resolve_backend()
    if backend != "bwrap":
        _last_bwrap_mount = None
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


def sandbox_status_line() -> str:
    try:
        backend = resolve_backend()
    except Exception as e:
        return f"沙箱：不可用（{e}）"
    if backend == "off":
        return f"沙箱：off（cwd={cfg.OUTPUT_DIR}）"
    if backend == "bwrap":
        mount = _last_bwrap_mount or SANDBOX_CWD
        return f"沙箱：bwrap → {cfg.OUTPUT_DIR} ⇔ {mount}"
    linked = False
    try:
        linked = Path(SANDBOX_CWD).is_symlink() and Path(SANDBOX_CWD).resolve() == cfg.OUTPUT_DIR.resolve()
    except OSError:
        pass
    cwd_hint = SANDBOX_CWD if linked else str(cfg.OUTPUT_DIR)
    return f"沙箱：landlock → 可写 {cfg.OUTPUT_DIR}；cwd={cwd_hint}"
