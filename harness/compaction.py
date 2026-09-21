"""上下文压缩：总字符超限时裁剪。

参数从 .env 读取（不经 harness.config）：
- CONTEXT_CHAR_LIMIT（默认 40000）
- KEEP_RECENT_AI_MESSAGES（默认 3）

规则：
- 总字符 ≤ CONTEXT_CHAR_LIMIT → 不裁剪
- 超限时：
  1. 保留全部用户输入（HumanMessage，不含系统 reminder）
  2. 非最近 KEEP_RECENT_AI_MESSAGES 条 AIMessage：调用大模型摘要
  3. 最近 KEEP_RECENT_AI_MESSAGES 条 AIMessage（及紧随其后的 ToolMessage）全量保留
  4. 排列：用户输入 → AI 较早消息摘要 → AI 最近 N 条全量（含其 ToolMessage）
"""

from __future__ import annotations

import json
import os

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, message_to_dict


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip().replace("_", ""))
    except ValueError:
        return default


def context_char_limit() -> int:
    return _env_int("CONTEXT_CHAR_LIMIT", 40_000)


def keep_recent_ai_messages() -> int:
    return _env_int("KEEP_RECENT_AI_MESSAGES", 3)


def todo_nag_rounds() -> int:
    return _env_int("TODO_NAG_ROUNDS", 3)


_SUMMARIZE_PROMPT = """请将以下「较早的助手回复」压缩为一段中文摘要（保留关键结论、决策、文件路径与错误信息；省略冗余工具噪声）。
只输出摘要正文，不要标题或代码围栏。

【较早助手回复】
{text}
"""


def _content_text(msg) -> str:
    c = getattr(msg, "content", "")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for p in c:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text", ""))
            elif isinstance(p, str):
                parts.append(p)
        return "\n".join(parts)
    return str(c or "")


def _is_user_human(msg) -> bool:
    if not isinstance(msg, HumanMessage):
        return False
    text = _content_text(msg).strip()
    return bool(text) and not text.startswith("<reminder>")


def estimate_size(messages: list) -> int:
    return sum(len(_content_text(m)) for m in messages)


def _ai_blocks(messages: list) -> list[list]:
    """按 AIMessage 分块：每块 = [AIMessage, 紧随的 ToolMessage...]。"""
    blocks: list[list] = []
    i = 0
    n = len(messages)
    while i < n:
        msg = messages[i]
        if isinstance(msg, AIMessage):
            block = [msg]
            i += 1
            while i < n and isinstance(messages[i], ToolMessage):
                block.append(messages[i])
                i += 1
            blocks.append(block)
        else:
            i += 1
    return blocks


def _format_ai_block(block: list) -> str:
    parts = []
    for m in block:
        if isinstance(m, AIMessage):
            text = _content_text(m)
            tcs = getattr(m, "tool_calls", None) or []
            if tcs:
                names = ", ".join(
                    (tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "?"))
                    for tc in tcs
                )
                parts.append(f"[AI tool_calls: {names}]\n{text}")
            else:
                parts.append(f"[AI]\n{text}")
        elif isinstance(m, ToolMessage):
            parts.append(f"[Tool {getattr(m, 'name', '') or ''}]\n{_content_text(m)[:4000]}")
    return "\n\n".join(parts)


def _summarize_older_ai(blocks: list[list]) -> str:
    blob = "\n\n-----\n\n".join(_format_ai_block(b) for b in blocks)
    blob = blob[:60000]
    try:
        from langchain_core.messages import HumanMessage as HM

        from agents.llm import make_llm

        llm = make_llm()
        resp = llm.invoke([HM(content=_SUMMARIZE_PROMPT.format(text=blob))])
        content = resp.content
        if isinstance(content, list):
            content = "\n".join(
                p.get("text", "") if isinstance(p, dict) else str(p) for p in content
            )
        text = str(content).strip()
        return text or "（摘要为空）"
    except Exception as e:
        # 回退：截断拼接，避免压缩失败导致上下文继续膨胀
        preview = blob[:3000]
        return f"（自动摘要失败：{e}）\n{preview}"


def compact_by_char_limit(messages: list, limit: int | None = None) -> list:
    """超限则按规则重建消息列表；未超限原样返回。"""
    if limit is None:
        limit = context_char_limit()
    if estimate_size(messages) <= limit:
        return messages

    humans = [m for m in messages if _is_user_human(m)]
    blocks = _ai_blocks(messages)
    keep_n = keep_recent_ai_messages()
    if len(blocks) <= keep_n:
        older, recent = [], blocks
    else:
        older, recent = blocks[:-keep_n], blocks[-keep_n:]

    out: list = list(humans)
    if older:
        print(
            f"  \033[36m[compact] 总字符>{limit}，"
            f"摘要 {len(older)} 段较早 AI，保留最近 {len(recent)} 段全量\033[0m"
        )
        summary = _summarize_older_ai(older)
        out.append(
            HumanMessage(
                content=f"<ai-history-summary>\n{summary}\n</ai-history-summary>"
            )
        )
    for block in recent:
        out.extend(block)

    # 若仍超限，对摘要再截断（极端情况）
    if estimate_size(out) > limit and out:
        # 压缩摘要本身
        for i, m in enumerate(out):
            if isinstance(m, HumanMessage) and _content_text(m).startswith("<ai-history-summary>"):
                text = _content_text(m)
                if len(text) > 8000:
                    out[i] = HumanMessage(content=text[:8000] + "\n…(摘要截断)")
                break
    return out


def prepare_context(messages: list) -> list:
    """入口：字符超限则裁剪并写回列表。"""
    compacted = compact_by_char_limit(messages)
    messages[:] = compacted
    return messages


# 兼容旧测试/引用
def message_to_dict_size(messages: list) -> int:
    return len(json.dumps([message_to_dict(m) for m in messages], default=str))
