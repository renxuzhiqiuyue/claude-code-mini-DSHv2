"""路径与运行时常量（纯 Python，无 LangChain 依赖）。

可配置项一律从 .env 读取（见工程根 `.env` / `.env.example`）。
OUTPUT_DIR 还可被 CLI `--output-dir` 覆盖。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]  # claude-code-mini/
MEMORY_DIR = ROOT / ".memory"
SKILLS_DIR = ROOT / "skills"

load_dotenv(ROOT / ".env", override=True, interpolate=True)
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip().replace("_", ""))
    except ValueError:
        return default


# —— 重试（.env）——
MAX_RETRIES = _env_int("MAX_RETRIES", 3)
BASE_DELAY_MS = _env_int("BASE_DELAY_MS", 500)

# —— 会话 thread（仅进程内 InMemory checkpointer；按会话目录名区分）——
THREAD_ID = (os.environ.get("THREAD_ID") or "mini-main").strip() or "mini-main"

# —— 权限规则（写死在代码，不从 .env 读）——
DENY_LIST = [
    "rm -rf /",
    "sudo",
    "shutdown",
    "reboot",
    "mkfs",
    "dd if=",
    "> /dev/sda",
]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777", "dd "]
# 另见 harness.permission._PY_DELETE_RE：os.remove / unlink / rmtree 等

# —— 输出目录（.env / CLI）——
OUTPUT_DIR: Path = ROOT / ".output"
TOOL_RESULTS_DIR: Path = OUTPUT_DIR / "tool-results"
OUTDIR = OUTPUT_DIR  # 兼容旧名


def _resolve_output_dir_arg(raw: str | Path | None) -> Path:
    """相对路径相对 ROOT；绝对路径原样解析。默认 .output。"""
    if raw is None or str(raw).strip() == "":
        return (ROOT / ".output").resolve()
    p = Path(str(raw).strip()).expanduser()
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def set_output_dir(raw: str | Path | None = None) -> Path:
    """设置全局 OUTPUT_DIR（及 TOOL_RESULTS_DIR / OUTDIR 别名）。"""
    global OUTPUT_DIR, TOOL_RESULTS_DIR, OUTDIR
    if raw is None or str(raw).strip() == "":
        raw = os.environ.get("OUTPUT_DIR") or ".output"
    OUTPUT_DIR = _resolve_output_dir_arg(raw)
    TOOL_RESULTS_DIR = OUTPUT_DIR / "tool-results"
    OUTDIR = OUTPUT_DIR
    os.environ["OUTPUT_DIR"] = str(OUTPUT_DIR)
    return OUTPUT_DIR


set_output_dir(os.environ.get("OUTPUT_DIR") or ".output")

# —— 命令沙箱（bash/python；见 harness/sandbox/）——
# auto（默认）| bwrap | landlock | off
# auto：优先 bwrap（映射 /workspace），否则 landlock-run（harness/bin/）
SANDBOX_BACKEND = (os.environ.get("SANDBOX_BACKEND") or "auto").strip().lower() or "auto"
SANDBOX_CWD = "/workspace"
_RUNTIME_DIRS_READY = False


def ensure_runtime_dirs() -> None:
    global _RUNTIME_DIRS_READY
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    from harness.memory import ensure_memory_files
    from harness.sandbox import ensure_workspace_link, sandbox_status_line

    ensure_memory_files()
    ensure_workspace_link(OUTPUT_DIR)
    if not _RUNTIME_DIRS_READY:
        print(f"  {sandbox_status_line()}")
        _RUNTIME_DIRS_READY = True


def resolve_output_path(p: str) -> Path:
    """模型相对路径映射到 OUTPUT_DIR；禁止逃逸。"""
    raw = (p or "").strip()
    if not raw:
        raise ValueError("路径为空")

    path = Path(raw)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        parts = path.parts
        strip_names = {".output", "output", OUTPUT_DIR.name}
        if parts and parts[0] in strip_names:
            path = Path(*parts[1:]) if len(parts) > 1 else Path(".")
        resolved = (OUTPUT_DIR / path).resolve()

    out_root = OUTPUT_DIR.resolve()
    if not resolved.is_relative_to(out_root):
        raise ValueError(f"路径逃逸输出目录 OUTPUT_DIR={out_root}: {p}")
    return resolved


def rel_to_output(path: Path) -> str:
    try:
        return str(path.relative_to(OUTPUT_DIR.resolve()))
    except ValueError:
        return str(path)
