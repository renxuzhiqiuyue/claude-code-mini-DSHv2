"""tavily_search：联网搜索（Tavily）。"""

from __future__ import annotations

import json
import os

from langchain_core.tools import tool


def _client():
    try:
        from tavily import TavilyClient
    except ImportError as e:
        raise RuntimeError("未安装 tavily-python，请 pip install tavily-python") from e
    api_key = (os.getenv("TAVILY_API_KEY") or "").strip().strip('"')
    if not api_key:
        raise RuntimeError("未设置 TAVILY_API_KEY，请在 .env 中配置")
    return TavilyClient(api_key=api_key)


@tool("tavily_search")
def tavily_search(
    query: str,
    search_depth: str = "basic",
    max_results: int = 5,
    topic: str = "general",
    include_answer: bool = True,
) -> str:
    """使用 Tavily 搜索互联网实时信息，适合查政策、新闻、公开数据。"""
    print(f"\033[33m→ tavily_search({query!r})\033[0m")
    try:
        resp = _client().search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            topic=topic,
            include_answer=include_answer,
        )
        out = json.dumps(resp, ensure_ascii=False, indent=2)
    except Exception as e:
        out = f"Tavily search 失败: {e}"
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out
