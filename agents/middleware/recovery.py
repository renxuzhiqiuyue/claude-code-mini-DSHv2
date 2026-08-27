"""s11 → @wrap_model_call 瞬态错误重试。"""

from __future__ import annotations

import random
import time

from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call

from harness.config import BASE_DELAY_MS, MAX_RETRIES


def _retry_delay(attempt: int) -> float:
    base = min(BASE_DELAY_MS * (2**attempt), 32000) / 1000
    return base + random.uniform(0, base * 0.25)


def _is_transient_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return (
        "ratelimit" in name
        or "429" in msg
        or "529" in msg
        or "overloaded" in msg
        or "timeout" in msg
        or "temporarily" in msg
    )


@wrap_model_call
def error_recovery_middleware(request: ModelRequest, handler) -> ModelResponse:
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return handler(request)
        except Exception as e:
            last_exc = e
            if not _is_transient_error(e):
                raise
            delay = _retry_delay(attempt)
            print(
                f"  \033[33m[recovery] 瞬态错误，重试 {attempt + 1}/{MAX_RETRIES} "
                f"等待 {delay:.1f}s\033[0m"
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]
