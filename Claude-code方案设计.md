# Claude-code-mini 方案设计

> 本目录实现小型 Claude Code。依据仓库根 [`docs/`](../docs/)，尤其 [`docs/s21-middleware-harness.md`](../docs/s21-middleware-harness.md)。  
> 范围：**MVP（s01–s03）+ 核心 Harness（至 s11）**。不做 MCP / 团队 / 后台 / Cron / 任务图 / Worktree。  
> 入口：**CLI（`python main.py`）+ Web 三栏页**（共享同一套 Agent）。  
> **实现要求：尽量用 LangChain 方式** — `create_agent` + middleware / `@tool`；手写 `while True` 仅作对照，不以之为主路径。

---

## 1. 定位与原则

**模型驾驶，本项目只造 Harness。** 循环由 LangGraph ReAct 承担；能力挂在 **middleware** 与 **tools** 上，不改写循环体。

1. **循环交给框架**：`langchain.agents.create_agent`（底层 LangGraph），不维护自研主循环。  
2. **扩展用 middleware**：权限、压缩、prompt、恢复等对标 docs Hook，映射到 `@before_agent` / `@before_model` / `@dynamic_prompt` / `@wrap_model_call` / `@wrap_tool_call` / `@after_agent`。  
3. **工具用 `@tool`**：bash / read / write / edit 等为 LangChain Tool；沙箱逻辑在 tool 实现内。  
4. **core 与 middleware 分层**：纯逻辑（路径、压缩算法、权限规则）放 `core/` 或工具模块，**不依赖** LangChain；middleware 只负责「何时调用」。  
5. **输出目录 vs `.memory/`**（见 §2）：工具产物进 `OUTPUT_DIR`（默认 `.output`）；记忆不走此前缀。  
6. **文案中文**：system prompt、工具 description、Skill、记忆、权限询问、REPL/Web。  
7. **Planner + Solver**：用户对接 Planner；复杂执行经 `solve_task` 交 Solver（独立模型，跑完销毁）。无邮箱队友。  
8. **双入口、单内核**：CLI / Web 都 `build_planner().invoke` / stream。

| 阶段 | docs | 要什么（LangChain 落点） |
|------|------|--------------------------|
| A. MVP | s01–s03 | `create_agent` + `@tool` 四工具 + `@wrap_tool_call` 权限 |
| B. 核心 | s04–s11 | middleware + Todo；**Planner + Solver**（`solve_task`） |
| C. Web | — | 三栏页调用同一 `build_agent()` |

对照实现：[`code/s21_middleware_harness/`](../code/s21_middleware_harness/)；机制语义对照 `../docs/s01`–`s11`。

---

## 2. `.output` / `.memory`

```
claude-code-mini/
├── .memory/
│   ├── MEMORY.md                 # SKILL 式：默认 L0+L3；L1/L2 经 load_memory
│   ├── .consolidate_state.json   # 已 Consolidation 的 session 列表
│   └── session_<启动时刻>.json   # 每个进程启动只建一个；Human/AI/Tool 交替 JSON
└── .output/                      # 默认工具输出目录（可启动时改）
```

| | 输出目录（默认 `.output/`） | `.memory/` |
|--|---------------------------|------------|
| 谁写 | Tool 执行（write/edit/bash、compact 落盘等） | **程序**确定性时机 |
| 前缀规则 | **是**（沙箱根） | **否** |
| 配置 | 变量 **`OUTPUT_DIR`** | 固定 `claude-code-mini/.memory/` |

**输出目录可配置（启动时选择）**

- 用 `main.py` 或 Web 启动时，可指定文件输出目录；**默认**为工程下的 `.output`。  
- 运行时用变量 **`OUTPUT_DIR`** 保存绝对/解析后的路径（环境变量、CLI 参数或 Web 表单均可写入同一变量）。  
- 示例：`OUTPUT_DIR=.output`（默认）；`OUTPUT_DIR=my_runs` 或绝对路径。相对路径相对 `claude-code-mini/` 解析。  
- 工具沙箱根 = `OUTPUT_DIR`：相对路径读写、`bash` 的 cwd、compact 大结果落盘均落于此；禁止逃逸该目录。  
- `.memory/` 仍不走输出前缀规则，不受 `OUTPUT_DIR` 影响。

**记忆分层**（`MEMORY.md` 对齐 SKILL.md：YAML frontmatter + 分节）

| 层 | 内容 | 存放 | Prompt |
|----|------|------|--------|
| L0 | 记忆种类与目的 | `MEMORY.md` 说明表 | **默认注入** |
| L1 | 短期：最近约 3 次问答摘要 | 进程内存 + session；Consolidation 写入短期段 | `load_memory("short")` |
| L2 | 长期：语义 / 情节 / 程序 | `MEMORY.md` | `load_memory("long")` |
| L3 | 用户画像与偏好 | `MEMORY.md` | **默认注入** |

**启动时 MEMORY Consolidation（`harness/memory/`）**

1. `MEMORY.md` **不存在** → 按模板新建（空画像/长期占位）。  
2. 扫描尚未 Consolidation、且含真实对话的 `session_*.json`（兼容旧 `.md`）；**没有** → 跳过，不调模型、不改 `MEMORY.md`。  
3. **有** → 只取其中**最新一次**会话原文 + 当前 `MEMORY.md`，调用大模型增量整理。  
4. 模型判断该会话有**新增或修改**信息 → 覆盖写入 `MEMORY.md`；输出 `[[NO_UPDATE]]` 或无有效更新 → **不修改** `MEMORY.md`。  
5. 无论是否写入，将该最新 session 记入 `.consolidate_state.json`，避免重复处理；更早的未 Consolidation 会话留待**下次启动**再处理。  
6. 规则：无证据不编造；已有足够则保留；不足只补缺口。  
7. 然后为本进程创建新的 `session_<启动时刻>.json`。

**会话 JSON（替代原 session_*.md）**

- 用户询问进入（`@before_agent`）、AI 生成结束（`@after_model`）、工具返回（`@wrap_tool_call`）、回合收尾（`@after_agent`）均增量写入。  
- 格式示例：

```json
{
  "source": "cli",
  "started_at": "2026-08-05 20:00:00",
  "messages": [
    {"HumanMessage": "用户原文"},
    {"AIMessage": "助手原文或 {content, tool_calls}"},
    {"ToolMessage": {"content": "...", "tool_call_id": "...", "name": "bash"}}
  ]
}
```

**上下文压缩（`harness/compaction.py`）**

- 触发：消息总字符数 > **200_000**。  
- 保留全部用户 `HumanMessage`；较早 AI 块（含其 ToolMessage）由大模型摘要；最近 **3** 段 AI（及紧随 ToolMessage）全量保留。  
- 排列：**用户输入 → AI 历史摘要 → 最近 3 段 AI 全量**。

- `session_*`：**启动** `main.py` / Web 时创建一次，多轮追加。  
- 相对路径工具产物 → `OUTPUT_DIR`（默认 `.output/`）；记忆不走该前缀。

---

## 3. 架构（LangChain）

```
User(CLI|Web)
    → create_agent(model, tools, middleware=STACK, checkpointer=...)
         @before_agent      输入护栏 / 注入
         @before_model      prepare_context（compact）
         @dynamic_prompt    中文 system（skills/memory/workspace）
         @wrap_model_call   429/529 退避、token 升级
         LLM + tool loop（框架）
         @wrap_tool_call    权限 → 执行 → 日志
         @after_agent       Stop / 收尾
```

| docs 机制 | LangChain 挂载 |
|-----------|----------------|
| Agent Loop | `create_agent` / LangGraph |
| Tools + 输出沙箱 | `@tool`（实现内解析到 `OUTPUT_DIR`） |
| Permission | `@wrap_tool_call`（或 HITL middleware） |
| Hooks | middleware 栈（等同事件总线） |
| Todo / Skill | `@tool` + `@before_model` / `@dynamic_prompt` |
| Solver | `solve_task` → 独立 `create_agent`（`SOLVER_MODEL_ID`，跑完销毁） |
| Compact | `@before_model`（总字符>20万：保留全部用户输入 + 摘要较早 AI + 最近3段 AI 全量） |
| Memory | 程序写 `.memory/session_*.json`（Human/AI/Tool 交替）；启动 Consolidation；`@dynamic_prompt` 只读注入 |
| Prompt 组装 | `@dynamic_prompt`（中文 sections） |
| Recovery | `@wrap_model_call` |

```python
def build_agent():
    return create_agent(
        model=make_llm(),          # ChatOpenAI / 兼容网关，读 .env
        tools=TOOLS,               # 中文 description；tools/ 下按能力注册
        middleware=MIDDLEWARE_STACK,
        checkpointer=get_planner_checkpointer(),  # Sqlite → .memory/checkpoints.db
        system_prompt="占位：由 @dynamic_prompt 覆盖",
    )
```

---

## 4. 双入口

### 4.1 CLI

```sh
cd claude-code-mini && python main.py
# 或：python -m serve.main
# 可选指定输出目录（写入 OUTPUT_DIR，默认 .output）：
#   python main.py --output-dir .output
#   OUTPUT_DIR=my_runs python main.py
# 内部：agents.build_agent().invoke(...)
```

### 4.2 Web（Phase C）

轻量 Web（FastAPI + 静态页）；**同一 `agents.build_agent()`**。入口：`serve/web_server.py`，前端在 `serve/web/`。顶栏可改输出目录，写入同一 **`OUTPUT_DIR`**（默认 `.output`）。破坏性 bash：SSE 推送 `permission` 事件，前端批准/拒绝后经 `POST /api/permission` 放行（HITL；硬拒绝名单仍直接拦）。

```sh
python -m serve.web_server
# → http://127.0.0.1:8765
```

```
┌─────────────┬──────────────────────┬─────────────────────┐
│ 左：目录树  │ 中：文件预览         │ 右：Agent 对话      │
│ skills/     │ 点击左侧文件         │ SSE 流式            │
│ .memory/    │ .md / 代码文本       │ 工具过程可见        │
│ OUTPUT_DIR/ │                      │                     │
└─────────────┴──────────────────────┴─────────────────────┘
```

**可见**：`skills/`、`.memory/`、当前 `OUTPUT_DIR`（默认 `.output/`）。  
**不可见**：`.env`、`agents/`、`harness/`、`tools/`、`serve/`、`db/`、`tests/`、`requirements.txt` 等。  

接口：`GET /api/tree`、`GET /api/file`、`POST /api/chat`（SSE，含 `permission`）、`POST /api/permission`、`GET|POST /api/settings`、`GET /api/health`。

---

## 5. 目录

```
claude-code-mini/
├── Claude-code方案设计.md  # 本方案
├── .env / .env.example
├── main.py                 # 便捷入口 → serve.main
├── requirements.txt
├── agents/                 # Agent 组装
│   ├── agent.py            # build_agent
│   ├── llm.py              # make_llm
│   └── middleware/         # permission / prompt / compaction / recovery / lifecycle
├── harness/                # 核心逻辑（供 middleware / tools 调用，无主循环）
│   ├── config.py           # ROOT / OUTPUT_DIR / MEMORY_DIR
│   ├── memory/             # 分层记忆 + 会话 jsonl + Consolidation
│   ├── permission.py
│   ├── compaction.py
│   ├── skills.py
│   └── todo.py
├── tools/                  # PLANNER/SOLVER 工具集；solve_task / text2sql / root_cause / tavily
├── db/                     # connection + MySQL manager
├── serve/                  # 启动方式
│   ├── main.py             # CLI
│   ├── web_server.py       # Web（Phase C）
│   └── web/                # 三栏静态前端（index + static）
├── tests/                  # 测试
├── skills/                 # planner/ · solver/ · shared/ 按角色隔离
├── .memory/                # MEMORY.md + session_*.json + .consolidate_state.json
└── .output/                # 默认 OUTPUT_DIR
```

配置：`MODEL_ID` + `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL`；**`OUTPUT_DIR`**；**`DB_*`**；可选 **`TAVILY_API_KEY`**。  
栈：Python 3.10+、**LangChain / LangGraph**、`python-dotenv`、FastAPI / uvicorn（SSE）。

---

## 6. 交付与验收

**Phase A**：`create_agent` + 四工具 `@tool` + 权限 `@wrap_tool_call`；确保 `OUTPUT_DIR`、`.memory/` 存在。  
验收：可在输出目录改文件跑命令；越界写 / `rm -rf /` 被拦；**主路径无手写 agent_loop**。

**Phase B**：middleware + Todo；Planner/Solver（`solve_task`，`SOLVER_MODEL_ID`）。  
验收：长会话可压；产物只在 `OUTPUT_DIR`；启动时按「最新未 Consolidation 会话」增量更新 `MEMORY.md`（无新信息不改、不存在则新建）；文案中文。

**Phase C**（已实现）：三栏 Web；左树仅 `skills` / `.memory` / `OUTPUT_DIR`；右栏同一 Agent + SSE；顶栏可改 `OUTPUT_DIR`。  

**对照**：语义看 `../docs/s01`–`s11`；组装看 `../docs/s21` 与 `../code/s21_middleware_harness/`。现有裸 Anthropic Phase A 代码应迁到 LangChain 主路径（可保留 core 纯函数）。
