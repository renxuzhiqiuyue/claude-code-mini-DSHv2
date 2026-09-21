"""HiAgent → 无状态 OpenAI LLM 网关配置。

直接改本文件常量后启动（见 README.md）。HIAGENT_BASE_URL、HIAGENT_API_KEY
来自智能体「发布 → API 接入」，不是方舟 Key。
"""

from __future__ import annotations

# ========== 在此填写 HiAgent 参数 ==========
HIAGENT_BASE_URL = "https://你的应用服务地址"
HIAGENT_API_KEY = ""
HIAGENT_USER_ID = "llm-gateway"
POOL_SIZE = 3
GATEWAY_API_KEY = "sk-hiagent-gateway"
GATEWAY_HOST = "0.0.0.0"
GATEWAY_PORT = 8080
MODEL_NAME = "hiagent"
CHAT_TIMEOUT_SEC = 300
# ==========================================


def api_root() -> str:
    """规范成 …/api/proxy/api/v1。"""
    base = (HIAGENT_BASE_URL or "").rstrip("/")
    suffix = "/api/proxy/api/v1"
    if base.endswith(suffix):
        return base
    return f"{base}{suffix}"


def validate() -> None:
    if not HIAGENT_API_KEY or "你的" in (HIAGENT_BASE_URL or ""):
        raise RuntimeError(
            "请在 hiagent2llm/config.py 填写 "
            "HIAGENT_BASE_URL 与 HIAGENT_API_KEY（智能体发布页 API 接入）"
        )
    if POOL_SIZE < 1:
        raise RuntimeError("POOL_SIZE 至少为 1")
