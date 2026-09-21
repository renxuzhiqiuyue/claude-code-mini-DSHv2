"""HiAgent 代理 API：create / list / chat / delete。"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

from hiagent2llm import config as cfg

logger = logging.getLogger("hiagent2llm.hiagent")

_client: httpx.AsyncClient | None = None


def _headers() -> dict[str, str]:
    key = cfg.HIAGENT_API_KEY
    return {
        "Apikey": key,
        "ApiKey": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def start() -> None:
    global _client
    cfg.validate()
    _client = httpx.AsyncClient(
        timeout=httpx.Timeout(cfg.CHAT_TIMEOUT_SEC, connect=30.0),
        headers=_headers(),
        follow_redirects=True,
    )


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _cli() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("HiAgent HTTP 客户端未启动")
    return _client


def _url(path: str) -> str:
    return f"{cfg.api_root()}/{path.lstrip('/')}"


def _extract_conversation_id(data: Any) -> str:
    if isinstance(data, str) and data.strip():
        return data.strip()
    if not isinstance(data, dict):
        return ""
    for key in ("AppConversationID", "appConversationID", "ConversationID", "conversation_id"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for nest in ("Conversation", "Data", "data", "Result", "Payload"):
        inner = data.get(nest)
        found = _extract_conversation_id(inner)
        if found:
            return found
    return ""


def _ensure_ok(data: Any, raw: str) -> None:
    if not isinstance(data, dict):
        return
    code = data.get("code", data.get("Code", data.get("StatusCode")))
    if code in (None, 0, "0", 200, "200", "success", "Success", "ok", "OK"):
        return
    msg = data.get("message") or data.get("Message") or data.get("msg") or raw[:400]
    raise RuntimeError(f"HiAgent API error: {code} {msg}")


def _extract_ids(data: Any) -> list[str]:
    ids: list[str] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = None
        for key in (
            "Conversations",
            "ConversationList",
            "AppConversationList",
            "AppConversations",
            "List",
            "Data",
            "data",
            "Items",
        ):
            val = data.get(key)
            if isinstance(val, list):
                items = val
                break
        if items is None:
            one = _extract_conversation_id(data)
            return [one] if one else []
    else:
        return []
    for item in items:
        cid = _extract_conversation_id(item)
        if cid:
            ids.append(cid)
    return ids


def _extract_answer(data: Any) -> str:
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return ""
    for key in ("answer", "Answer", "content", "Content", "Output", "text", "delta"):
        val = data.get(key)
        if isinstance(val, str) and val:
            return val
    for nest in ("Data", "data", "Message", "message", "Result"):
        inner = data.get(nest)
        found = _extract_answer(inner)
        if found:
            return found
    return ""


async def create_conversation() -> str:
    resp = await _cli().post(
        _url("create_conversation"),
        json={"Inputs": {}, "UserID": cfg.HIAGENT_USER_ID},
    )
    resp.raise_for_status()
    payload = resp.json()
    _ensure_ok(payload, resp.text)
    cid = _extract_conversation_id(payload)
    if not cid:
        raise RuntimeError(f"create_conversation 未返回 AppConversationID: {resp.text[:400]}")
    logger.info("created conversation %s", cid)
    return cid


async def list_conversations() -> list[str]:
    resp = await _cli().post(
        _url("get_conversation_list"),
        json={"UserID": cfg.HIAGENT_USER_ID},
    )
    resp.raise_for_status()
    payload = resp.json()
    _ensure_ok(payload, resp.text)
    ids = _extract_ids(payload)
    logger.info("listed %s conversations for %s", len(ids), cfg.HIAGENT_USER_ID)
    return ids


async def delete_conversation(conversation_id: str) -> None:
    if not conversation_id:
        return
    resp = await _cli().post(
        _url("delete_conversation"),
        json={"AppConversationID": conversation_id, "UserID": cfg.HIAGENT_USER_ID},
    )
    resp.raise_for_status()
    try:
        payload = resp.json()
    except Exception:
        payload = None
    if payload is not None:
        _ensure_ok(payload, resp.text)
    logger.info("deleted conversation %s", conversation_id)


async def reset(conversation_id: str) -> str:
    """删除后再创建；失败时不额外 create，由调用方把槽作废。"""
    await delete_conversation(conversation_id)
    return await create_conversation()


def compose_query(user_text: str) -> str:
    return (user_text or "").strip()


async def chat(conversation_id: str, user_text: str) -> str:
    payload = {
        "ResponseMode": "blocking",
        "AppConversationID": conversation_id,
        "UserID": cfg.HIAGENT_USER_ID,
        "Query": compose_query(user_text),
    }
    resp = await _cli().post(_url("chat_query_v2"), json=payload)
    resp.raise_for_status()
    ctype = (resp.headers.get("content-type") or "").lower()
    if "text/event-stream" in ctype or resp.text.lstrip().startswith("data:"):
        last = ""
        for raw in resp.text.splitlines():
            line = raw.strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if not body or body == "[DONE]":
                continue
            try:
                chunk = json.loads(body)
            except json.JSONDecodeError:
                last = body
                continue
            ans = _extract_answer(chunk)
            if ans:
                last = ans
        return last
    data = resp.json()
    _ensure_ok(data, resp.text)
    answer = _extract_answer(data)
    if not answer:
        logger.warning("empty answer: %s", resp.text[:400])
    return answer


async def chat_stream(conversation_id: str, user_text: str) -> AsyncIterator[str]:
    payload = {
        "ResponseMode": "streaming",
        "AppConversationID": conversation_id,
        "UserID": cfg.HIAGENT_USER_ID,
        "Query": compose_query(user_text),
    }
    prev = ""
    async with _cli().stream("POST", _url("chat_query_v2"), json=payload) as resp:
        resp.raise_for_status()
        async for raw in resp.aiter_lines():
            line = (raw or "").strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if not body or body == "[DONE]":
                continue
            try:
                chunk = json.loads(body)
            except json.JSONDecodeError:
                yield body
                continue
            event = str(chunk.get("event") or "").lower()
            if event in {"error", "failed"}:
                raise RuntimeError(_extract_answer(chunk) or body)
            ans = _extract_answer(chunk)
            if not ans:
                continue
            if ans.startswith(prev):
                delta = ans[len(prev) :]
                prev = ans
                if delta:
                    yield delta
            else:
                prev = ans
                yield ans
