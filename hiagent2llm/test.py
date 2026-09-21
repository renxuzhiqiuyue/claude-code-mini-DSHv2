"""测试已启动的 hiagent2llm 是否已把智能体转成 OpenAI 兼容 llm_url。

先在已激活的环境中启动网关：
    ./hiagent2llm/bash-hiagent2llm.sh

再另开终端运行：
    python hiagent2llm/test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from hiagent2llm import config as cfg  # noqa: E402


def llm_url() -> str:
    host = "127.0.0.1" if cfg.GATEWAY_HOST in ("0.0.0.0", "::") else cfg.GATEWAY_HOST
    return f"http://{host}:{cfg.GATEWAY_PORT}/v1"


def _ok(name: str, detail: str = "") -> None:
    extra = f"  {detail}" if detail else ""
    print(f"[OK] {name}{extra}")


def _fail(name: str, detail: str) -> None:
    print(f"[FAIL] {name}  {detail}")
    raise SystemExit(1)


def test_health(client) -> None:
    r = client.get("/health")
    if r.status_code != 200:
        _fail("/health", f"HTTP {r.status_code} {r.text[:300]}")
    data = r.json()
    if not data.get("ok"):
        _fail("/health", str(data))
    _ok("/health", f"pool={data.get('pool_size')} alive={data.get('alive')} model={data.get('model')}")


def test_models(client) -> None:
    r = client.get("/v1/models", headers={"Authorization": f"Bearer {cfg.GATEWAY_API_KEY}"})
    if r.status_code != 200:
        _fail("/v1/models", f"HTTP {r.status_code} {r.text[:300]}")
    ids = [m.get("id") for m in (r.json().get("data") or [])]
    if cfg.MODEL_NAME not in ids:
        _fail("/v1/models", f"未看到 {cfg.MODEL_NAME}: {ids}")
    _ok("/v1/models", str(ids))


def test_openai_chat() -> str:
    from openai import OpenAI

    url = llm_url()
    client = OpenAI(api_key=cfg.GATEWAY_API_KEY, base_url=url, timeout=cfg.CHAT_TIMEOUT_SEC)
    resp = client.chat.completions.create(
        model=cfg.MODEL_NAME,
        messages=[
            {"role": "system", "content": "只回复一个汉字：好"},
            {"role": "user", "content": "请只回复：好"},
        ],
        stream=False,
    )
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        _fail("OpenAI chat.completions", "choices[0].message.content 为空")
    _ok("OpenAI chat.completions", f"llm_url={url}  reply={content[:80]!r}")
    return content


def test_langchain_chat() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    url = llm_url()
    llm = ChatOpenAI(
        model=cfg.MODEL_NAME,
        api_key=cfg.GATEWAY_API_KEY,
        base_url=url,
        temperature=0,
        max_tokens=64,
        timeout=cfg.CHAT_TIMEOUT_SEC,
    )
    resp = llm.invoke([
        SystemMessage(content="只回复一个汉字：好"),
        HumanMessage(content="请只回复：好"),
    ])
    content = (resp.content or "").strip() if isinstance(resp.content, str) else str(resp.content)
    if not content:
        _fail("LangChain ChatOpenAI", "content 为空")
    _ok("LangChain ChatOpenAI", f"base_url={url}  reply={content[:80]!r}")


def main() -> None:
    import httpx

    url = llm_url()
    print(f"llm_url = {url}")
    print(f"model   = {cfg.MODEL_NAME}")
    try:
        with httpx.Client(base_url=url.rsplit("/v1", 1)[0], timeout=15.0) as client:
            test_health(client)
            test_models(client)
    except httpx.ConnectError:
        _fail(
            "连接网关",
            f"无法连接 {url} ，请先运行 ./hiagent2llm/bash-hiagent2llm.sh",
        )
    test_openai_chat()
    test_langchain_chat()
    print("全部通过：智能体已转化为 OpenAI 兼容 llm_url")


if __name__ == "__main__":
    main()
