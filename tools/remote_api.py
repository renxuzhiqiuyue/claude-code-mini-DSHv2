"""比赛远程 API：统一鉴权 GET（X-App-Id / X-App-Key）。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


def remote_get(path: str, params: dict | None = None, *, timeout: float = 30.0) -> str:
    """GET {TOOL_BASE_URL}{path}?…，返回响应正文或错误字符串。"""
    base = (os.getenv("TOOL_BASE_URL") or "").strip().rstrip("/")
    app_id = (os.getenv("TOOL_APP_ID") or "").strip()
    app_key = (os.getenv("TOOL_APP_KEY") or "").strip()
    if not base:
        return "错误：未设置 TOOL_BASE_URL，请在 .env 中配置"
    if not app_id or not app_key:
        return "错误：未设置 TOOL_APP_ID / TOOL_APP_KEY，请在 .env 中配置"

    clean = {
        k: v
        for k, v in (params or {}).items()
        if v is not None and str(v).strip() != ""
    }
    qs = urllib.parse.urlencode(clean)
    url = f"{base}{path}?{qs}" if qs else f"{base}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "X-App-Id": app_id,
            "X-App-Key": app_key,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        # 尽量格式化 JSON
        try:
            return json.dumps(json.loads(body), ensure_ascii=False, indent=2)
        except Exception:
            return body
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return f"远程调用失败 HTTP {e.code}: {detail or e.reason}"
    except Exception as e:
        return f"远程调用失败: {e}"
