"""bash：经 OS 沙箱执行（默认 bwrap，工作区映射为 /workspace）。"""

from __future__ import annotations

from langchain_core.tools import tool

from harness import config as cfg
from harness.sandbox_exec import SANDBOX_CWD, last_bwrap_mount, prepare_sandbox_workdir, run_bash, sandbox_backend, sandbox_status_line


def _normalize_command(command: str) -> str:
    """去掉模型常多写的宿主机 / .output 前缀，改为沙箱相对路径。"""
    out = cfg.OUTPUT_DIR.resolve()
    abs_slash = str(out).replace("\\", "/") + "/"
    normalized = command.replace("\\", "/")
    prefixes = [
        abs_slash,
        f"{out.name}/",
        ".output/",
        "./.output/",
        "output/",
        f"{SANDBOX_CWD}/",
    ]
    alt = last_bwrap_mount()
    if alt and alt != SANDBOX_CWD:
        prefixes.extend([f"{alt}/", alt])
        normalized = normalized.replace(f"{SANDBOX_CWD}/", "")
        normalized = normalized.replace(SANDBOX_CWD, alt)
    for prefix in sorted(set(prefixes), key=len, reverse=True):
        if prefix and prefix in normalized:
            normalized = normalized.replace(prefix, "")
    return normalized


def _run(command: str) -> str:
    prepare_sandbox_workdir()
    command = _normalize_command(command)
    try:
        r = run_bash(command, timeout=120)
        # 过滤 landlock launcher 的信息行，避免干扰模型
        err_lines = [
            ln
            for ln in (r.stderr or "").splitlines()
            if ln.strip()
            and "partial enforcement" not in ln
            and not ln.startswith("landlock-run: partial")
        ]
        out = "\n".join(
            x for x in [(r.stdout or "").strip(), "\n".join(err_lines).strip()] if x
        ).strip()
        if r.returncode != 0 and not out:
            out = f"（退出码 {r.returncode}，无输出）"
        elif r.returncode != 0:
            out = f"{out}\n[exit code: {r.returncode}]"
        return out[:50000] if out else "（无输出）"
    except Exception as e:
        name = type(e).__name__
        if "Timeout" in name:
            return "错误：超时（120 秒）"
        return f"错误：{e}"


@tool
def bash(command: str) -> str:
    """在文件沙箱中执行 shell（bash / python3）。

    沙箱内当前目录为 /workspace（对应宿主机 OUTPUT_DIR）。
    路径请写相对名：joke.md、data/a.json；不要写 .output/ 或宿主机绝对路径。
    请使用 python3。
    """
    print(f"\033[33m→ bash({command!r})  [{sandbox_status_line()}]\033[0m")
    out = _run(command)
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out
