# Claude-code-mini

小型 Claude Code：用 **LangChain `create_agent` + middleware + `@tool`** 搭 Harness。  
对外入口是 **Planner**；复杂执行交给 **Solver**（`solve_task`，独立 `SOLVER_MODEL_ID`）。

详细设计见 [`Claude-code方案设计.md`](Claude-code方案设计.md)；机制语义对照仓库根 `docs/s01`–`s11`、`docs/s21`。

## 它做什么

| | 说明 |
|--|------|
| Planner（主） | 简单问答；复杂事先 `todo_write`，再 `solve_task` 交 Solver |
| Solver | 启动时预检模型；每次 `solve_task` 创建、执行、返回总结后销毁 |
| 工具沙箱 | bash/python 经 **bwrap 或 landlock**；优先把产物目录呈现为 `/workspace` |
| 记忆 | 仅 Planner：默认注入种类+画像；每会话 `.memory/session_*/session.jsonl` |
| Skill | `skills/{planner,solver,shared}/*/SKILL.md`，按角色隔离 `load_skill` |
| 入口 | `python main.py`（选会话）· `python -m serve.web_server`（Web 选会话） |

不做：MCP、多 Agent 邮箱团队、后台 Cron、任务图、Worktree。

## 快速开始

```sh
cd claude-code-mini
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Planner_* / Solver_*

python main.py              # 交互：新建或打开 .memory/session_*/
python main.py --new        # 强制新建
python -m serve.web_server  # http://127.0.0.1:8765 ，浏览器内选会话
```

## 环境变量

| 变量 | 含义 |
|------|------|
| `Planner_API_KEY` / `Planner_BASE_URL` / `Planner_MODEL_ID` | **Planner**（必填） |
| `Solver_API_KEY` / `Solver_BASE_URL` / `Solver_MODEL_ID` | **Solver**（可选，缺省回退 Planner_*） |
| `OUTPUT_DIR` | 工具输出目录，默认 `.output` |
| `SANDBOX_BACKEND` | `auto`（默认）/ `bwrap` / `landlock` / `off`；二进制见 `harness/bin/` |
| `DB_*` / `TAVILY_API_KEY` | SQL·根因 / 联网（Solver 侧常用） |

## Planner / Solver 工具

| | Planner | Solver |
|--|---------|--------|
| bash / filesystem | ✓ | ✓ |
| todo_write | ✓ | ✗ |
| solve_task | ✓（委派） | ✗ |
| load_skill / tavily | ✓ | ✓ |
| 比赛远程/本地工具 | ✓ | ✓ |
| load_memory | ✓ | ✗（Solver 不读写用户记忆） |
| text2sql / root_cause | ✗ | ✓ |

## 目录结构

```
claude-code-mini/
├── agents/          # build_planner、llm（Planner/Solver）、middleware
├── harness/         # config / memory / permission / compaction / skills / todo
├── tools/           # PLANNER_TOOLS / SOLVER_TOOLS；solve_task.py
├── serve/           # CLI + Web（对话 / 轨迹 JSONL）
├── monitor-agent/   # .memory 会话浏览器（:40000）
├── skills/          # planner/ · solver/ · shared/
├── .memory/         # MEMORY.md + session_*/session.jsonl + solver/
└── …
```

## Middleware

| 机制 | 落点 |
|------|------|
| Planner Prompt | `@dynamic_prompt` |
| 权限 HITL | Planner / Solver 各自 `@wrap_tool_call` |
| Compact + Todo 提醒 | `@before_model` |
| Recovery | `@wrap_model_call` |
| Memory | lifecycle |
| Solver 委派 | `solve_task` → 独立 `create_agent`（`SOLVER_MODEL_ID`） |

## Skill 提示

`load_skill("plan-and-solve")`：先规划 / `todo_write`，再 `solve_task`。

## 测试

```sh
python -m tests.test_smoke
python tests/test_tools_smoke.py
```
