"""filesystem：OUTPUT_DIR 内的读 / 写 / 编辑工具。"""

from __future__ import annotations

from langchain_core.tools import tool

from harness.config import rel_to_output, resolve_output_path


def _read(path: str, limit: int | None = None) -> str:
    try:
        fp = resolve_output_path(path)
        if not fp.exists():
            return f"错误：文件不存在 {path}"
        lines = fp.read_text(encoding="utf-8").splitlines()
        if limit is not None and limit < len(lines):
            lines = lines[:limit] + [f"...（还有 {len(lines) - limit} 行）"]
        text = "\n".join(lines)
        return text[:50000] if text else "（空文件）"
    except Exception as e:
        return f"错误：{e}"


def _write(path: str, content: str) -> str:
    try:
        fp = resolve_output_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"已写入 {len(content)} 字节到 OUTPUT_DIR/{rel_to_output(fp)}"
    except Exception as e:
        return f"错误：{e}"


def _edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = resolve_output_path(path)
        if not fp.exists():
            return f"错误：文件不存在 {path}"
        text = fp.read_text(encoding="utf-8")
        if old_text not in text:
            return f"错误：在 {path} 中未找到要替换的文本"
        fp.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"已编辑 OUTPUT_DIR/{rel_to_output(fp)}"
    except Exception as e:
        return f"错误：{e}"


@tool("read_file")
def read_file(path: str, limit: int | None = None) -> str:
    """读取 OUTPUT_DIR 内的文件。path 为相对路径，自动映射到输出目录。"""
    print(f"\033[33m→ read_file({path!r})\033[0m")
    out = _read(path, limit)
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out


@tool("write_file")
def write_file(path: str, content: str) -> str:
    """将内容写入 OUTPUT_DIR（可新建）。path 为相对路径，自动映射到输出目录。"""
    print(f"\033[33m→ write_file({path!r})\033[0m")
    out = _write(path, content)
    print(out)
    return out


@tool("edit_file")
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """在 OUTPUT_DIR 内的文件中精确替换一段文本（只替换第一次出现）。"""
    print(f"\033[33m→ edit_file({path!r})\033[0m")
    out = _edit(path, old_text, new_text)
    print(out)
    return out
