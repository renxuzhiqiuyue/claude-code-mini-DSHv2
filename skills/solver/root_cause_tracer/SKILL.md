---
name: root-cause-tracer
description: 当需要对指标异动做根因下钻分析或生成决策树图时使用本 Skill。定义当期 vs 基期归因算法（固定 2 层、5+其他、方案 B 全局下钻），提供 CLI 验证与 generate_drill_tree 出图。与 read-root-cause 共用同一套规则。
---

# 根因下钻算法 Skill

## 概述

本 Skill 定义 **指标异动归因的下钻规则**、**决策树 JSON 结构** 与 **本地脚本**。Agent 在线分析走 read-root-cause（`fetch_period_data` → `build_root_cause_tree`）；离线 CSV 验证走 `drill_engine.py`；决策树 PNG 走 `generate_drill_tree.py`。三者算法一致。

## 工作区与路径约定

- cwd = `OUTPUT_DIR`（默认 `.output/`，工具沙箱根）
- 根因：`data/root_01.json`；报告：`report.md`；决策树：`images/chart_root.png`
- 出图：`python ../skills/solver/root_cause_tracer/scripts/generate_drill_tree.py --run-dir .`

## 核心能力

- 固定 **2 层**下钻（dimensions ≥ 2），不得超过 2 层
- 每层输出 **全部候选维度** 的解释力得分，标注主因维度
- 取值展示：**Top5 +「其他」**（>5 个取值时）
- **方案 B**：第 2 层在排除「其他」后的子集上 **全局** 下钻
- 生成决策树 `tree` 结构并输出 `chart_root.png`

## 何时使用

**必须加载本 Skill 当：**

- 需要理解或验证根因下钻算法规则
- 框架含 root_xx / 第五章变化原因，需出决策树图
- 执行 `drill_engine.py` 或 `generate_drill_tree.py`
- 编写或审查根因相关 Markdown / JSON

**配合使用：** read-root-cause（Agent 工具调用）、yijiu-huanxin-reporter（第五章写法）。

## 工作流程

### 步骤 1：在线根因（Agent）

```
fetch_period_data → build_root_cause_tree (output_format=both)
→ write_file data/root_01.json
```

### 步骤 2：生成决策树

在 **OUTPUT_DIR**（默认 `.output/`）下执行：

```bash
python ../skills/solver/root_cause_tracer/scripts/generate_drill_tree.py --run-dir .
```

输出 `images/chart_root.png`，嵌入 `【图：根因下钻决策树】`。

### 步骤 3：离线验证（可选）

在 OUTPUT_DIR 或任意目录执行（CSV 路径自定）：

```bash
python ../skills/solver/root_cause_tracer/scripts/drill_engine.py drill \
  ../skills/solver/root_cause_tracer/sample_data/sample_gbk.csv \
  --period-col period --metrics trans_amt \
  --dimensions prod_tp,rec_city_nm --format json
```

---

## 算法要点

| 概念 | 说明 |
|------|------|
| 单指标 | 每次只分析一个数值列，如 `trans_amt` |
| 多维度 | 逗号分隔，建议 ≥ 2 |
| 解释力得分 | 同向 delta 之和；上升取最大维度，下降取最负 |
| 5 + 「其他」 | 取值 > 5：Top5 + 合并「其他」；≤5 全部展示 |
| 第 2 层（方案 B） | 排除「其他」后全局下钻，仅一条第 2 层路径 |
| 决策树结构 | 非「其他」取值 → 汇合节点 → D2 → 取值 |

### 两层下钻示意

```
整体 delta
  → D1（解释力最大）→ Top5 +「其他」
  → 非「其他」汇合 → D2（解释力最大）→ Top5 +「其他」
  → chart_root.png
```

### 决策树图结构

```
[metric Δ] → [D1 解释力] → 取值… 「其他」(叶子)
              取值1 ──┐
              取值2 ──┼→ [汇合] → [D2 解释力] → 取值…
```

---

## 与 read-root-cause 的分工

| 场景 | 使用 |
|------|------|
| SQLite 根因取数 | read-root-cause |
| 算法 / CLI / 出图 | 本 Skill |
| 报告第五章 | yijiu-huanxin-reporter |

`build_root_cause_tree` 返回：`drill_path[]`、`tree`、`markdown`。

---

## 环境与 CLI

依赖：`graphviz`（`pip install graphviz` + 系统 `apt install graphviz`）

| 脚本 | 用途 |
|------|------|
| `drill_engine.py validate` | 校验 CSV |
| `drill_engine.py drill` | 下钻分析 |
| `generate_drill_tree.py` | 生成 PNG |

---

## 返回结构示例

```json
{
  "success": true,
  "metric": "trans_amt",
  "overall": { "delta": 89300, "direction": "up" },
  "drill_path": [
    {
      "step": 1,
      "dimension": "prod_tp",
      "dimension_score": 89300,
      "all_dimension_scores": { "prod_tp": 89300, "rec_city_nm": 42100 },
      "display_values": [{ "value": "家电", "delta": 60300, "is_other": false }]
    }
  ],
  "tree": { "nodes": [], "edges": [] }
}
```

---

## 报告写作要求

第五章须含：整体异动 → 第 1/2 层得分表与取值 → **【图：根因下钻决策树】** → 业务解读。禁止只写一层或省略得分表。

---

## 规则

1. 禁止不读长表手写归因
2. dimensions ≥ 2 时必须 2 层，禁止超过 2 层
3. 禁止省略任一层全维度解释力得分
4. 修改算法须同步 `root_cause_utils.py` 与 `drill_engine.py`

---

## 故障排查

| 现象 | 处理 |
|------|------|
| 只有 1 层 | 检查 dimensions ≥ 2 |
| 无得分表 | 确认 `all_dimension_scores` 字段 |
| 出图失败 | 检查 graphviz 与 root_01.json 中 `tree` |
| 周期标签错误 | 统一 period 与 current/base label |
