---
name: plan-and-solve
description: Plan-and-Solve 范式（Planner）。多步骤任务先 todo_write / 可选写 plan.md，再用 solve_task 交给 Solver 执行。用户要先规划再执行、或交办复杂任务时使用。
---

# Plan-and-Solve Skill（Planner 侧）

本 Skill 给 **Planner** 用。执行侧是独立的 **Solver**（`solve_task` → `SOLVER_MODEL_ID`），Solver 负责执行、不再规划、不委派。

## 工作区

- 沙箱 = `OUTPUT_DIR`（默认 `.output/`）
- 可选计划文件：`plan.md`（相对 OUTPUT_DIR）

```
OUTPUT_DIR/
├── plan.md       ← 可选：Planner 写出计划
└── …             ← Solver 执行产物
```

## 何时使用

- 多步骤、写文件、查库、根因、出报告等复杂任务
- 需要把「未完成 todo」交给 Solver

闲聊 / 简单问答：Planner 直接回答即可，不必 `solve_task`。

## 工作流程

### 1. Plan（Planner）

1. （推荐）`write_file("plan.md", …)` 写清目标与步骤  
2. `todo_write`：拆成 `pending` / `in_progress`  
3. 需要规范时 `load_skill(...)`

### 2. Solve（交 Solver，**一次一项**）

```
todo_write(...)   # 仅将一个待办标为 in_progress
solve_task(description="可选：仅针对当前这一步的补充说明")
```

- **每次 `solve_task` 只委派一个待办**（优先 `in_progress`，否则首个 `pending`）
- **禁止**一次委派多个步骤，或在同一轮多次 `solve_task`
- 须等 Solver 返回、更新 todo 后，再 `solve_task` 处理下一项
- Solver 可用：bash / filesystem / load_skill（仅 `skills/solver/`+`shared/`）/ tavily / SQL / 根因  
- Solver **没有** `todo_write` / `solve_task` / `load_memory`；**不读不写**用户记忆  
- Planner 技能仅见 `skills/planner/` + `skills/shared/`；执行类 skill 在 `skills/solver/`  
- 返回总结字符串后本次 Solver 销毁（过程不写入 `.memory/`）  

### 3. 收尾（Planner）

- 根据 Solver 总结将**当前项**标为 `completed`（或保留 `in_progress` 并补充说明）  
- 若还有剩余待办：将下一项标为 `in_progress`，再单独 `solve_task`  

## Agent 自检

- [ ] 复杂任务已 `todo_write`  
- [ ] 执行类工作走了 `solve_task`，而非 Planner 硬扛 SQL/根因  
- [ ] 已消化 Solver 返回的总结  
