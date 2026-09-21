# hiagent2llm

把 HiAgent 智能体发布 API 转成 **无状态** 的 OpenAI `POST /v1/chat/completions`。  
调用方按 OpenAI / LangChain 用法请求；网关内部用固定数量的 HiAgent 会话槽，问完就删再建，占用条数不增加。

本目录独立于 HiAgent 控制台，参数只写在 `config.py`，不读 `.env`。

## 1. 填写配置

编辑 `hiagent2llm/config.py`（来自智能体「发布 → API 接入」，不是方舟 Key）：

```python
HIAGENT_BASE_URL = "https://你的应用服务地址"
HIAGENT_API_KEY = "发布后拿到的 Apikey"
HIAGENT_USER_ID = "llm-gateway"
POOL_SIZE = 2                    # 建议 1～4，小于平台会话上限
GATEWAY_API_KEY = "sk-hiagent-gateway"
GATEWAY_HOST = "0.0.0.0"
GATEWAY_PORT = 8080
MODEL_NAME = "hiagent"
```

`HIAGENT_BASE_URL` 写应用根地址即可，程序会自动补 `/api/proxy/api/v1`。

## 2. 启动

```bash
./hiagent2llm/bash-hiagent2llm.sh
```

在已经激活 conda / `.venv` 的终端里执行即可，脚本只负责 `python -m hiagent2llm`。监听地址和端口来自 `config.py`。

服务地址：`http://127.0.0.1:8080/v1`  
健康检查：`GET /health`  
模型列表：`GET /v1/models`

## 3. 调用方式

### OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-hiagent-gateway",          # GATEWAY_API_KEY
    base_url="http://127.0.0.1:8080/v1",
)
resp = client.chat.completions.create(
    model="hiagent",
    messages=[
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "上一轮问题"},
        {"role": "assistant", "content": "上一轮回答"},
        {"role": "user", "content": "现在问什么"},
    ],
)
print(resp.choices[0].message.content)
```

### LangChain / claude-code-mini

```python
ChatOpenAI(
    api_key="sk-hiagent-gateway",
    base_url="http://127.0.0.1:8080/v1",
    model="hiagent",
)
```

把 `.env` 的 `Planner_BASE_URL` / `Solver_BASE_URL` 指到 `http://127.0.0.1:8080/v1`，`*_API_KEY` 填 `GATEWAY_API_KEY` 即可。`model` 用网关配置的 `MODEL_NAME` 或任意字符串（网关不校验）。

## 4. 请求怎么走

```
客户端  POST /v1/chat/completions
        messages（system / user / assistant / tool 都会保留）
           │
           ▼
     从池里借一个空闲槽（没有就等待，绝不新建超出 POOL_SIZE 的会话）
           │
           ▼
     把 messages 拼成一句 Query
     chat_query_v2(AppConversationID, Query, ResponseMode=blocking|streaming)
           │
           ▼
     把正文包成 OpenAI choices[0].message
           │
           ▼
     delete_conversation → create_conversation → 新 ID 放回同一槽
```

- 槽位在请求期间加锁，避免两次调用写进同一个会话。
- `stream: true` 时等 SSE 结束后再删除重建。
- 进程启动先 `get_conversation_list`：多于 `POOL_SIZE` 的删掉，不足的再创建；重启沿用这批 ID。
- `reset` 失败则该槽作废并打日志，**不会再多开一个会话**。

## 5. 发给后台智能体的格式

`POST {HIAGENT_BASE_URL}/api/proxy/api/v1/chat_query_v2`

```http
Apikey: <HIAGENT_API_KEY>
Content-Type: application/json
```

```json
{
  "ResponseMode": "blocking",
  "AppConversationID": "池里借到的会话ID",
  "UserID": "llm-gateway",
  "Query": "……拼好的纯文本……"
}
```

HiAgent 没有 OpenAI `messages` / `tools` 字段。网关把整段对话（含 tool 调用与返回）写进这一句 `Query`。只有一条 user 时，`Query` 就是那句话；有多轮时类似：

```text
请根据下面的完整对话回答最后一条用户问题。对话中可能包含工具调用与工具返回。

[system]
……

[user]
用户原话

[assistant]
tool_call id=call_xxx name=todo_write
{"todos":[...]}

[tool name=todo_write tool_call_id=call_xxx]
工具返回正文
```

`tools`、`tool_choice`、`temperature`、`max_tokens` 不会转给后台。后台每次问完都会删会话再建，**平台侧没有上一轮上下文**；历史只存在本次 `Query` 里。

## 6. 文件

| 文件 | 作用 |
|------|------|
| `config.py` | 全部参数（写死，不读环境变量） |
| `app.py` | `/v1/models`、`/v1/chat/completions` |
| `hiagent.py` | create / chat / delete |
| `pool.py` | 固定槽位、锁、用完重置 |
| `bash-hiagent2llm.sh` | 启动脚本 |
