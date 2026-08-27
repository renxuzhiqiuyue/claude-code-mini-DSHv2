"""从 MEMORY.md 抽取层，供 prompt / load_memory。"""

from __future__ import annotations

import re

from harness.memory import paths, runtime
from harness.memory.files import ensure_memory_files, parse_frontmatter


def extract_section(md: str, heading: str) -> str:
    aliases = {
        "记忆种类与目的": ["记忆种类与目的", "第0层：记忆种类与目的"],
        "用户画像与偏好": ["用户画像与偏好", "第三层：用户画像与偏好"],
        "短期记忆": ["短期记忆", "第一层：短期记忆"],
        "长期记忆": ["长期记忆", "第二层：长期记忆"],
    }
    names = aliases.get(heading, [heading])
    for name in names:
        pattern = rf"^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)"
        m = re.search(pattern, md, re.M | re.S)
        if m:
            return m.group(1).strip()
    return ""


def memory_core_for_prompt() -> str:
    ensure_memory_files()
    raw = paths.MEMORY_FILE.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    kinds = extract_section(body if meta else raw, "记忆种类与目的")
    profile = extract_section(body if meta else raw, "用户画像与偏好")
    parts = []
    desc = meta.get("description") or "用户分层记忆；短期/长期请 load_memory 按需加载。"
    parts.append(f"**说明**：{desc}")
    if kinds:
        parts.append("### 记忆种类与目的\n" + kinds)
    if profile:
        parts.append("### 用户画像与偏好\n" + profile)
    if not kinds and not profile:
        parts.append("（MEMORY.md 暂无种类/画像内容）")
    return "\n\n".join(parts)


def load_memory_layer(layer: str, *, limit: int = 8000) -> str:
    ensure_memory_files()
    key = (layer or "").strip().lower()
    raw = paths.MEMORY_FILE.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    src = body if meta else raw

    if key in ("core", "default"):
        return memory_core_for_prompt()
    if key in ("kinds", "kind", "catalog", "index"):
        return extract_section(src, "记忆种类与目的") or "（无记忆种类表）"
    if key in ("profile", "pref", "preferences", "l3"):
        return extract_section(src, "用户画像与偏好") or "（无用户画像与偏好）"
    if key in ("short", "short_term", "l1"):
        parts = []
        if runtime.short_term:
            lines = []
            for i, item in enumerate(runtime.short_term, 1):
                lines.append(f"{i}. 问：{item['user'][:200]}")
                if item.get("summary"):
                    lines.append(f"   答要：{item['summary'][:400]}")
            parts.append("【本进程工作记忆】\n" + "\n".join(lines))
        sec = extract_section(src, "短期记忆")
        if sec and "（最近约三次" not in sec and "暂无" not in sec:
            parts.append("【MEMORY.md · 短期记忆】\n" + sec)
        return ("\n\n".join(parts) if parts else "（无短期记忆）")[:limit]
    if key in ("long", "long_term", "l2"):
        return (extract_section(src, "长期记忆") or "（无长期记忆）")[:limit]
    if key in ("all", "full"):
        return raw.strip()[: max(limit, 12000)]
    return f"错误：未知 layer={layer!r}。可用：core / kinds / profile / short / long / all"
