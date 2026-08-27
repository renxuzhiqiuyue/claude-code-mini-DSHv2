"""rag_search：本地 Hybrid RAG 检索（调用 rag_agent_new FastAPI）。

前置：启动 RAG 服务，例如：
  bash /home/langchain_learning/rag_agent_new/bash-server.sh
接口：POST {RAG_API_BASE_URL}/v1/retrieve  （默认 http://127.0.0.1:8300）
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from langchain_core.tools import tool

DEFAULT_BASE = "http://127.0.0.1:8300"
DEFAULT_CORPUS = "test_md"
RETRIEVE_PATH = "/v1/retrieve"


def _base_url() -> str:
    return (os.getenv("RAG_API_BASE_URL") or DEFAULT_BASE).strip().rstrip("/")


def _default_corpus() -> str:
    return (os.getenv("RAG_CORPUS") or DEFAULT_CORPUS).strip() or DEFAULT_CORPUS


def _post_retrieve(payload: dict, *, timeout: float = 120.0) -> dict:
    url = f"{_base_url()}{RETRIEVE_PATH}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _format_response(data: dict) -> str:
    """压成 Agent 友好的摘要 JSON，避免整包 debug 过大。"""
    results = []
    for ctx in data.get("contexts") or []:
        results.append(
            {
                "doc_title": ctx.get("doc_title") or "",
                "section": ctx.get("section") or "",
                "source": ctx.get("source") or "",
                "rerank_score": ctx.get("rerank_score"),
                "content": ctx.get("merged_content") or "",
            }
        )
    out = {
        "query_original": data.get("query_original"),
        "query_rewritten": data.get("query_rewritten"),
        "result_count": len(results),
        "results": results,
    }
    pipeline = (data.get("debug") or {}).get("pipeline")
    if pipeline:
        out["pipeline"] = pipeline
    return json.dumps(out, ensure_ascii=False, indent=2)


@tool("rag_search")
def rag_search(
    query: str,
    corpus: str = "",
    top_k: int = 5,
    recall_k: int = 20,
) -> str:
    """检索本地知识库（Hybrid RAG），适合查制度、规范、内部文档等已入库内容。

    与 tavily_search（联网）互补：本工具只查本地索引，不访问互联网。
    
    参数：
        query: 查询语句
        corpus: 知识库名称
        recall_k: 初步筛选的数量，默认 5，不能超过 10
        top_k: 最终返回的检索结果数量，默认 3, 不能超过 5
        
    """
    corpus_name = (corpus or "").strip() or _default_corpus()
    top_k = max(1, int(top_k))
    recall_k = max(top_k, int(recall_k))
    print(f"\033[33m→ rag_search({query!r}, corpus={corpus_name!r}, top_k={top_k})\033[0m")

    payload = {
        "query": query,
        "corpus": corpus_name,
        "top_k": top_k,
        "recall_k": recall_k,
    }
    try:
        data = _post_retrieve(payload)
        out = _format_response(data)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
        out = (
            f"rag_search 失败 HTTP {e.code}: {detail or e.reason}\n"
            f"请确认服务已启动: bash /home/langchain_learning/rag_agent_new/bash-server.sh\n"
            f"健康检查: curl {_base_url()}/health"
        )
    except Exception as e:
        out = (
            f"rag_search 失败: {e}\n"
            f"请确认 RAG 服务在 {_base_url()} 可用 "
            f"(bash /home/langchain_learning/rag_agent_new/bash-server.sh)"
        )

    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out
