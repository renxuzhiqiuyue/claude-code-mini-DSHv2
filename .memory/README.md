# `.memory/` 说明

- `MEMORY.md`：分层用户记忆（Consolidation 更新）
- `session_<slug>/`：每个 Planner 会话一个文件夹
  - `session.jsonl`：轨迹事件流
  - `solver/session_*.jsonl`：该会话下的 Solver 子轨迹
- `.consolidate_state.json`：已 Consolidation 的会话目录名

不再使用 `checkpoints.db`；多轮对话仅进程内 InMemory，跨重启以 JSONL 为轨迹存档。

## JSONL 事件类型

| type | 含义 |
|------|------|
| `session/meta` | 会话头 |
| `user/message` | 用户 |
| `assistant/message` | 助手（可含 `tool_calls`） |
| `tool/call` / `tool/result` | 工具 |
| `subagent/start` / `subagent/end` | Solver 起止（写在父 `session.jsonl`） |

启动时 CLI 交互选择「新建 / 续聊」；Web 在首页弹层选择。
