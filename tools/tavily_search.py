"""tavily_search：联网搜索桩（当前无网络，不发起真实请求）。"""

from __future__ import annotations

from langchain_core.tools import tool

OFFLINE_REPLY = "【当前出于无网络环境中，请直接使用大模型能力回答】"


@tool("tavily_search")
def tavily_search(
    query: str,
    search_depth: str = "basic",
    max_results: int = 5,
    topic: str = "general",
    include_answer: bool = True,
) -> str:
    """联网搜索互联网实时信息。当前为无网络环境，调用后会提示改用大模型自身知识作答。"""
    print(f"\033[33m→ tavily_search({query!r}) [offline]\033[0m")
    print(OFFLINE_REPLY)
    return OFFLINE_REPLY
