"""OpenAI 兼容网关：POST /v1/chat/completions ，对调用方无状态。"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from hiagent2llm import config as cfg
from hiagent2llm import hiagent
from hiagent2llm.pool import pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("hiagent2llm.app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await hiagent.start()
    await pool.start()
    logger.info(
        "gateway up  model=%s  pool=%s  api=%s",
        cfg.MODEL_NAME,
        cfg.POOL_SIZE,
        cfg.api_root(),
    )
    yield
    await hiagent.close()


app = FastAPI(title="HiAgent OpenAI Gateway", lifespan=lifespan)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: Any = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: Any = None
    function_call: Any = None


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


def _authorize(authorization: str | None) -> None:
    expected = (cfg.GATEWAY_API_KEY or "").strip()
    if not expected:
        return
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid GATEWAY_API_KEY")


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in (None, "text"):
                parts.append(str(item.get("text") or ""))
        return "\n".join(p for p in parts if p.strip()).strip()
    if content is None:
        return ""
    return str(content).strip()


def _dump_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _format_tool_calls(tool_calls: Any) -> str:
    if not tool_calls:
        return ""
    if not isinstance(tool_calls, list):
        return _dump_json(tool_calls)
    lines: list[str] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            lines.append(_dump_json(call))
            continue
        fn = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = fn.get("name") or call.get("name") or ""
        args = fn.get("arguments", call.get("arguments", ""))
        cid = call.get("id") or ""
        bits = ["tool_call"]
        if cid:
            bits.append(f"id={cid}")
        if name:
            bits.append(f"name={name}")
        lines.append(" ".join(bits))
        if args not in (None, ""):
            lines.append(_dump_json(args))
    return "\n".join(lines).strip()


def _format_turn(msg: ChatMessage) -> tuple[str, str] | None:
    role = (msg.role or "user").strip().lower() or "user"
    extra = msg.model_extra or {}
    additional = extra.get("additional_kwargs") if isinstance(extra.get("additional_kwargs"), dict) else {}
    tool_calls = msg.tool_calls or additional.get("tool_calls")
    function_call = msg.function_call or additional.get("function_call")
    header = role
    if msg.name:
        header += f" name={msg.name}"
    if msg.tool_call_id:
        header += f" tool_call_id={msg.tool_call_id}"
    parts: list[str] = []
    text = _content_text(msg.content)
    if text:
        parts.append(text)
    tool_text = _format_tool_calls(tool_calls)
    if tool_text:
        parts.append(tool_text)
    if function_call:
        parts.append("function_call: " + _dump_json(function_call))
    if not parts:
        return None
    return header, "\n".join(parts)


def _messages_to_query(messages: list[ChatMessage]) -> str:
    """HiAgent 只收一句 Query：把 OpenAI messages（含 tool）拼成完整对话再发出去。"""
    turns: list[tuple[str, str]] = []
    has_user = False
    for msg in messages:
        formatted = _format_turn(msg)
        if formatted is None:
            continue
        header, body = formatted
        turns.append((header, body))
        role = (msg.role or "").strip().lower()
        if role == "user":
            has_user = True
    if not has_user:
        raise HTTPException(status_code=400, detail="messages 中没有 user 内容")
    if len(turns) == 1 and turns[0][0] == "user":
        return turns[0][1]
    lines = [
        "请根据下面的完整对话回答最后一条用户问题。对话中可能包含工具调用与工具返回。",
        "",
    ]
    for header, body in turns:
        lines.append(f"[{header}]")
        lines.append(body)
        lines.append("")
    return "\n".join(lines).strip()


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _completion_body(cid: str, model: str, content: str) -> dict:
    return {
        "id": cid,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _chunk(cid: str, model: str, delta: str | None, finish: str | None = None) -> str:
    body = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": delta} if delta is not None else {},
                "finish_reason": finish,
            }
        ],
    }
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "pool_size": cfg.POOL_SIZE,
        "alive": pool.alive_count(),
        "model": cfg.MODEL_NAME,
    }


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    return {
        "object": "list",
        "data": [
            {
                "id": cfg.MODEL_NAME,
                "object": "model",
                "created": 0,
                "owned_by": "hiagent2llm",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    req: ChatRequest,
    authorization: str | None = Header(default=None),
):
    _authorize(authorization)
    query = _messages_to_query(req.messages)
    model = (req.model or cfg.MODEL_NAME).strip() or cfg.MODEL_NAME
    cid = _completion_id()
    try:
        slot = await pool.acquire()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    if req.stream:

        async def event_stream() -> AsyncIterator[str]:
            try:
                async for delta in hiagent.chat_stream(slot.conversation_id, query):
                    if delta:
                        yield _chunk(cid, model, delta)
                yield _chunk(cid, model, None, finish="stop")
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.exception("stream chat failed")
                yield _chunk(cid, model, f"[hiagent error] {e}", finish="stop")
                yield "data: [DONE]\n\n"
            finally:
                await pool.finish(slot)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        answer = await hiagent.chat(slot.conversation_id, query)
        return JSONResponse(_completion_body(cid, model, answer))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("blocking chat failed")
        raise HTTPException(status_code=502, detail=str(e)) from e
    finally:
        await pool.finish(slot)
