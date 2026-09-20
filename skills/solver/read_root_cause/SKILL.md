---
name: read-root-cause
description: 当需要对指标异动做根因下钻（当期 vs 基期）时使用本 Skill。说明 fetch_period_data、build_root_cause_tree 的调用方法、SQL 长表示例与返回结构。下钻规则见 root-cause-tracer（固定 2 层、5+其他、方案 B）。须在 yijiu-huanxin-reporter 框架含 root_xx 时调用。
---

# 根因下钻工具 Skill

## 概述

本 Skill 说明 **root_cause 工具**（`tools/root_cause.py`） 的两个工具：`fetch_period_data`、`build_root_cause_tree`。从 SQLite 长表取数、校验、两层下钻归因，并产出 JSON / Markdown / 决策树结构。表名字段见 read-sql-data；算法见 root-cause-tracer；报告写法见 yijiu-huanxin-reporter。

## 工作区与路径约定

- cwd = `OUTPUT_DIR`（默认 `.output/`，工具沙箱根）
- 根因落盘：`data/root_01.json`
- 决策树：`python ../skills/solver/root_cause_tracer/scripts/generate_drill_tree.py --run-dir .`

## 核心能力

- `fetch_period_data`：UNION ALL 长表 SQL，校验 period / metric / dimensions
- `build_root_cause_tree`：固定 2 层下钻，全维度解释力得分，5+其他，方案 B
- 返回 `drill_path`、`tree`（供 generate_drill_tree 出图）、`markdown`
- 支持 inline data 或 cache_id（>500 行）

## 何时使用

**必须加载本 Skill 当：**

- 框架含 root_xx / 第五章变化原因分析
- 需要调用 `fetch_period_data` 或 `build_root_cause_tree`
- 需要编写 UNION ALL 根因 SQL

**必须按序调用：** 先 fetch（valid=true），再 build。**禁止** 用 `sql_db_query` 预览代替 fetch。

## 工作流程

### 步骤 1：fetch_period_data

编写 UNION ALL 长表 SQL → 调用 fetch → 确认 `valid=true`，取得 `data` 或 `cache_id`。

### 步骤 2：build_root_cause_tree

传与 fetch 一致的 metric、dimensions、period_col、labels；`output_format=both`。

### 步骤 3：落盘与出图

`write_file data/root_01.json` → `load_skill(root-cause-tracer)` → 在 OUTPUT_DIR 下执行：

```bash
python ../skills/solver/root_cause_tracer/scripts/generate_drill_tree.py --run-dir .
```

### 步骤 4：写入报告第五章

使用返回的 markdown + 决策树图，配合 yijiu-huanxin-reporter 深度写作规范。

---

## 工具概览

| 工具 | 作用 | 顺序 |
|------|------|------|
| `fetch_period_data` | 执行 UNION ALL SQL，取当期/基期长表并校验 | **1** |
| `build_root_cause_tree` | 单指标、多维度 **固定下钻 2 层**（不得超过），每层标注 **全部维度解释力得分** | **2**（仅当 fetch `valid=true`） |

---

## 核心概念

| 概念 | 说明 |
|------|------|
| **单指标** | 每次只分析一个数值列，如 `trans_amt` |
| **多维度** | 逗号分隔多个维度列，如 `prod_tp,rec_city_nm,eng_grade`；**建议 ≥ 2** |
| **长表** | 一行 = 一个 period + 各维度取值 + 一个 metric 聚合值 |
| **当期 / 基期** | 月报根因常用 **单月 vs 上月**（与月报「当年累计」口径不同） |
| **5 + 「其他」** | 取值 > 5：Top5 + 合并「其他」；≤5 全部展示 |
| **第 2 层（方案 B）** | 排除第 1 层「其他」后，在 Top5 子集上 **全局** 下钻一次 |
| **固定下钻 2 层** | dimensions ≥ 2 时必须 2 层；**禁止超过 2 层** |

### 时间口径（单月对比示例）

| 标签 | 含义 | WHERE 示例 |
|------|------|------------|
| 当期 | 报告月 | `trans_dt >= '2025-12-01' AND trans_dt < '2026-01-01'` |
| 基期 | 上一个月 | `trans_dt >= '2025-11-01' AND trans_dt < '2025-12-01'` |

`current_label` / `base_label` 必须与 SQL 中 period 列字面量一致（默认 `当期` / `基期`）。

---

## SQL 长表模板

**必须满足**：

1. `UNION ALL` 合并当期、基期两段 SELECT
2. 含 `period_col`（如 `'当期' AS period`）
3. 含 **一个** metric 列（已 `SUM` 聚合）
4. 含 **全部** dimensions 列（已在 GROUP BY 中）
5. 仅 SELECT；JOIN/过滤参考 `read-sql-data`

```sql
SELECT '当期' AS period,
       t.prod_tp, t.rec_city_nm, t.eng_grade,
       ROUND(SUM(t.trans_amt), 2) AS trans_amt
FROM yjhx_trans_detail t
JOIN usr_dim u ON t.usr_id = u.usr_id
WHERE t.trans_dt >= '2025-12-01' AND t.trans_dt < '2026-01-01'
  AND t.act_nm LIKE '%以旧换新%'
GROUP BY t.prod_tp, t.rec_city_nm, t.eng_grade

UNION ALL

SELECT '基期' AS period,
       t.prod_tp, t.rec_city_nm, t.eng_grade,
       ROUND(SUM(t.trans_amt), 2) AS trans_amt
FROM yjhx_trans_detail t
JOIN usr_dim u ON t.usr_id = u.usr_id
WHERE t.trans_dt >= '2025-11-01' AND t.trans_dt < '2025-12-01'
  AND t.act_nm LIKE '%以旧换新%'
GROUP BY t.prod_tp, t.rec_city_nm, t.eng_grade
```

（全国口径：不加 `branch_org_nm`。若 outline 指定分公司，两段 SELECT 的 WHERE 均追加 `AND u.branch_org_nm LIKE '%关键字%'`。）

对应工具参数：`period_col=period`, `metric=trans_amt`, `dimensions=prod_tp,rec_city_nm,eng_grade`

---

## Step 1：fetch_period_data

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `sql` | 是 | 上述 UNION ALL 长表 SQL |
| `metric` | 是 | 单个指标列名，须出现在 SQL SELECT 中 |
| `dimensions` | 是 | 逗号分隔，须全部出现在 SQL 中 |
| `period_col` | 否 | 默认 `period` |
| `current_label` | 否 | 默认 `当期` |
| `base_label` | 否 | 默认 `基期` |

### 调用示例

```
工具: fetch_period_data
参数:
  sql: |
    SELECT '当期' AS period, t.prod_tp, t.rec_city_nm, t.eng_grade,
           ROUND(SUM(t.trans_amt), 2) AS trans_amt
    FROM yjhx_trans_detail t
    JOIN usr_dim u ON t.usr_id = u.usr_id
    WHERE t.trans_dt >= '2025-12-01' AND t.trans_dt < '2026-01-01'
      AND t.act_nm LIKE '%以旧换新%'
    GROUP BY t.prod_tp, t.rec_city_nm, t.eng_grade
    UNION ALL
    SELECT '基期' AS period, t.prod_tp, t.rec_city_nm, t.eng_grade,
           ROUND(SUM(t.trans_amt), 2) AS trans_amt
    FROM yjhx_trans_detail t
    JOIN usr_dim u ON t.usr_id = u.usr_id
    WHERE t.trans_dt >= '2025-11-01' AND t.trans_dt < '2025-12-01'
      AND t.act_nm LIKE '%以旧换新%'
    GROUP BY t.prod_tp, t.rec_city_nm, t.eng_grade
  period_col: period
  metric: trans_amt
  dimensions: prod_tp,rec_city_nm,eng_grade
  current_label: 当期
  base_label: 基期
```

### 可能返回

**成功 · 小数据（≤500 行，inline）**：

```json
{
  "valid": true,
  "source": "sqlite",
  "row_count": 120,
  "columns": ["period", "prod_tp", "rec_city_nm", "eng_grade", "trans_amt"],
  "period_values": ["基期", "当期"],
  "metric": "trans_amt",
  "dimensions": ["prod_tp", "rec_city_nm", "eng_grade"],
  "data": [{ "period": "当期", "prod_tp": "家电", "trans_amt": "1000.00" }]
}
```

→ Step 2 传 `data` 字段。

**成功 · 大数据（>500 行）**：

```json
{
  "valid": true,
  "cache_id": "a1b2c3d4e5f6....json",
  "row_count": 1200,
  "metric": "trans_amt",
  "dimensions": ["prod_tp", "rec_city_nm", "eng_grade"],
  "message": "数据已缓存（1200 行），请用 cache_id 调用 build_root_cause_tree"
}
```

→ Step 2 传 `cache_id`。

**失败（不得进入 Step 2）**：

```json
{
  "valid": false,
  "errors": [
    "列不存在: prod_tp",
    "周期列中未找到当期标签: 当期"
  ]
}
```

| 错误类型 | 常见原因 | 修复 |
|----------|----------|------|
| 列不存在 | 字段名与 DDL 不符 | 对照 `read-sql-data` 改 SQL |
| 未找到当期/基期标签 | period 字面量与 label 不一致 | 统一 `'当期'`/`'基期'` 或改 label 参数 |
| 指标非数值 | metric 列含非数字 | SQL 中用 SUM 聚合数值列 |
| 查询为空 | WHERE 过严 | 放宽时间/地域条件 |

---

## Step 2：build_root_cause_tree

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `metric` | 是 | 与 Step 1 一致 |
| `dimensions` | 是 | 与 Step 1 一致（逗号分隔） |
| `data` | 二选一 | Step 1 返回的 `data` 数组 |
| `cache_id` | 二选一 | Step 1 返回的 `cache_id` |
| `period_col` | 否 | 默认 `period` |
| `current_label` / `base_label` | 否 | 与 Step 1 一致 |
| `cum_threshold` | 否 | 累计贡献阈值，默认 `0.6` |
| `output_format` | 否 | `json` / `markdown` / `both`（推荐 `both`） |

### 调用示例（使用 cache_id）

```
工具: build_root_cause_tree
参数:
  cache_id: a1b2c3d4e5f6....json
  metric: trans_amt
  dimensions: prod_tp,rec_city_nm,eng_grade
  period_col: period
  current_label: 当期
  base_label: 基期
  cum_threshold: 0.6
  output_format: both
```

### 调用示例（使用 data，小数据）

```
工具: build_root_cause_tree
参数:
  data: [{ "period": "当期", "prod_tp": "家电", "rec_city_nm": "长春", "eng_grade": "一级", "trans_amt": "50000" }]
  metric: trans_amt
  dimensions: prod_tp,rec_city_nm,eng_grade
  output_format: both
```

### 可能返回（output_format=both）

```json
{
  "result": {
    "success": true,
    "metric": "trans_amt",
    "overall": {
      "current": 1500000.0,
      "base": 1200000.0,
      "delta": 300000.0,
      "rate": 0.25,
      "direction": "up"
    },
    "drill": {
      "step": 1,
      "dimension": "prod_tp",
      "dimension_score": 280000.0,
      "all_dimension_scores": {
        "prod_tp": 280000.0,
        "rec_city_nm": 95000.0,
        "eng_grade": 12000.0
      },
      "selected_values": [
        {
          "value": "家电",
          "current": 800000.0,
          "base": 650000.0,
          "delta": 150000.0,
          "contribution_rate": 0.5
        }
      ]
    },
    "drill_path": [
      {
        "step": 1,
        "dimension": "prod_tp",
        "dimension_score": 280000.0,
        "all_dimension_scores": {
          "prod_tp": 280000.0,
          "rec_city_nm": 95000.0,
          "eng_grade": 12000.0
        },
        "selected_values": [
          {
            "value": "家电",
            "delta": 150000.0,
            "contribution_rate": 0.5
          }
        ]
      },
      {
        "step": 2,
        "dimension": "rec_city_nm",
        "dimension_score": 62000.0,
        "all_dimension_scores": {
          "rec_city_nm": 62000.0,
          "eng_grade": 8000.0
        },
        "selected_values": [
          {
            "value": "上海市",
            "delta": 45000.0,
            "contribution_rate": 0.15
          }
        ]
      }
    ]
  },
  "markdown": "## 根因分析报告\n\n### 整体\n...\n\n### 下钻路径\n\n**第 1 层 — 主因维度 `prod_tp`** ..."
}
```

**字段解读**：

| 字段 | 含义 |
|------|------|
| `overall.direction` | `up` 上升 / `down` 下降 / `flat` 持平（flat 时无 drill） |
| `overall.rate` | 变化率 = delta / base |
| `drill_path[].step` | 下钻层序号（1、2…） |
| `drill_path[].all_dimension_scores` | **该层全部候选维度** 的解释力得分（**必须写入报告**） |
| `drill_path[].dimension` | 该层选中的主因维度（解释力最强） |
| `drill_path[].dimension_score` | 选中维度的解释力得分 |
| `drill_path[].selected_values[].contribution_rate` | 该取值对 **整体** delta 的贡献占比 |
| `drill` | 第 1 层结果（兼容字段，与 `drill_path[0]` 一致） |
| `markdown` | 含各层维度得分表；可直接写入 reporter「变化原因分析」章 |

**失败示例**：

```json
{
  "success": false,
  "errors": ["数据为空，请先调用 fetch_period_data"]
}
```

---

## 调用前检查清单

调用前逐项确认，减少重试：

```
- [ ] 已 load_skill(yijiu-huanxin-reporter)，框架含 root_xx
- [ ] 已 load_skill(read-sql-data)，确认表名与 metric/维度字段存在
- [ ] SQL 为 UNION ALL，两段 period 标签与 current_label/base_label 一致
- [ ] SELECT 含 period_col + 1 个 metric + 全部 dimensions，且已 GROUP BY
- [ ] fetch_period_data 返回 valid=true
- [ ] build 的 metric、dimensions、period_col、labels 与 fetch 完全一致
- [ ] build 使用 fetch 返回的 data 或 cache_id（二选一，勿混用臆造）
```

## 规则

1. **禁止**跳过 fetch 直接 build
2. **禁止**用 sql_db_query 代替 fetch
3. fetch 失败只改 SQL/参数，不编造归因结论
4. 每次任务只分析 **一个** metric；换指标需重新 fetch + build
5. **dimensions ≥ 2 时禁止只写第一层或超过两层**；报告须含 **恰好两层** 下钻及每层 **全维度解释力得分表**
