---
name: read-sql-data
description: 以旧换新月报 MySQL 取数。提供 DDL（create_tables.sql）、字段取值（common_values.md）与 sql_db_query 调用规范。当查询条数为0，或者join后，查询条数为0后，可以加载这个技能包。
includes:
  - create_tables.sql
  - common_values.md
---

# MySQL 取数 Skill

## 工作区与路径约定

- cwd = `OUTPUT_DIR`（默认 `.output/`，工具沙箱根）
- 路径相对 OUTPUT_DIR：`data/query_xx.json` 等
- **禁止** 逃逸 OUTPUT_DIR；**禁止** 无必要的 `bash mkdir`（`write_file` 会自动建父目录）

## 概述

以旧换新业务库取数 Skill。`load_skill` 自动附带：

| 文件 | 内容 |
|------|------|
| `create_tables.sql` | 5 张表 DDL（权威字段） |
| `common_values.md` | 字段取值、分公司列表、品类映射 |

## 表关联

```
                    iss_ins_dim
                         ↑ iss_ins_id_cd
card_info ──usr_id──→ usr_dim ←──usr_id── yjhx_trans_detail ──mchnt_cd──→ mchnt_dim
    ↑ card_no                              (事实表)
    └──────────────────────────────────────┘
```

```sql
FROM yjhx_trans_detail t
JOIN usr_dim u ON t.usr_id = u.usr_id          -- 分公司 / 用户属性（常用）
JOIN mchnt_dim m ON t.mchnt_cd = m.mchnt_cd    -- 商户 / 收单（按需）
```

字段详情见 `create_tables.sql`；取值见 `common_values.md`。

## 业务口径（必遵）

### 时间：用 `trans_dt`（`YYYY-MM-DD`）

`trans_dt` 为 `DATE`，**WHERE 中的日期字面量必须带横杠**，格式 `YYYY-MM-DD`（如 `'2025-01-01'`）。

| 写法 | 是否正确 |
|------|----------|
| `t.trans_dt >= '2025-01-01'` | ✅ |
| `t.trans_dt = '20250101'` | ❌ 无横杠 |
| `t.rec_dt >= '2025-01-01'` | ❌ 收货日期，非月报口径 |

```sql
-- 2025 年全年累计
t.trans_dt >= '2025-01-01' AND t.trans_dt <= '2025-12-31'

-- 2025 年 12 月单月
t.trans_dt >= '2025-12-01' AND t.trans_dt <= '2025-12-31'
```

### 地域：分公司 vs 城市（两种口径，不可混用）

先判断用户问的是**分公司**还是**城市**：

| 用户说法 | 口径 | 字段 | 是否 JOIN `usr_dim` |
|----------|------|------|---------------------|
| **上海分公司** 交易笔数 | 分公司 scope | `u.branch_org_nm = '上海分公司'` | **必须** |
| **上海市** 以旧换新交易笔数 | 收货城市 | `t.rec_city_nm = '上海市'` | 不需要（除非还要用户属性） |
| 月报 scope「XX分公司/XX省」 | 分公司 scope | `u.branch_org_nm = 'XX分公司'` | **必须** |
| 城市分布（query_06） | 收货城市 | `t.rec_city_nm` | 建议 JOIN（配合 scope） |

**上海分公司 ≠ 上海市**：前者是组织机构（`usr_dim`），后者是收货地（事实表 `rec_city_nm`）。

```sql
-- ① 上海分公司的以旧换新交易笔数（须 JOIN usr_dim）
SELECT COUNT(*) AS trans_cnt,
       ROUND(SUM(t.trans_amt), 2) AS trans_amt
FROM yjhx_trans_detail t
JOIN usr_dim u ON t.usr_id = u.usr_id
WHERE u.branch_org_nm = '上海分公司'
  AND t.trans_dt >= '2025-01-01' AND t.trans_dt <= '2025-11-30'
  AND t.act_nm LIKE '%以旧换新%';

-- ② 上海市的以旧换新交易笔数（收货城市，用 rec_city_nm）
SELECT COUNT(*) AS trans_cnt,
       ROUND(SUM(t.trans_amt), 2) AS trans_amt
FROM yjhx_trans_detail t
WHERE t.rec_city_nm = '上海市'
  AND t.trans_dt >= '2025-01-01' AND t.trans_dt <= '2025-11-30'
  AND t.act_nm LIKE '%以旧换新%';
```

| 常见误写 | 原因 |
|----------|------|
| `rec_city_nm = '上海'` | 库内为 `'上海市'`，且不能代表分公司 |
| 问「上海分公司」却不 JOIN `usr_dim` | 缺少 `branch_org_nm` 条件 |
| `trans_dt = '20250101'`（无横杠） | 须写 `'2025-01-01'` 等 `YYYY-MM-DD` |
| 用 `rec_dt` 过滤月报 | 月报时间口径只用 `trans_dt` |

**禁止**用 `rec_city_nm` 代替分公司 scope。**禁止**对 `branch_org_nm` 使用 `LIKE`。

### 活动 / 品类

```sql
t.act_nm LIKE '%以旧换新%'                              -- 合计
t.act_nm LIKE '%以旧换新%' AND t.prod_tp = '家电'       -- 家电
t.prod_tp = '手机数码3C'                                -- 手机数码
t.prod_tp = '家居家装'                                  -- 家居家装
```

## 工具链

| 工具 | 用途 |
|------|------|
| `sql_db_query_checker` | 校验 SQL（每条必先调用） |
| `sql_db_query` | 执行 SELECT |
| `write_file` | 缓存至 `data/query_xx.json` |
| `sql_db_table_schema` | 列报错时核对 |

顺序：**checker → query → write_file**。默认不调用 `sql_db_list_tables`。

JSON 格式：`{"sql":"...", "rows":[...], "row_count": N}`

## 0 行结果：必做校验（不可一次就结束）

`sql_db_query` 返回 `row_count: 0` 或 `COUNT(*)=0` 时，**先假定 WHERE 取值或关联条件有误**，对照 `common_values.md` 与上文「业务口径」排查并重写 SQL，**至少修正后再查一次**。禁止把 0 行直接当「暂无数据」写进报告。

### 1. 检查 WHERE 里的字面量

| 排查项 | 常见错误 | 正确做法 |
|--------|----------|----------|
| 地域口径混用 | 问「上海分公司」却用 `rec_city_nm` | 分公司 → `JOIN usr_dim` + `u.branch_org_nm = '上海分公司'` |
| 城市名不完整 | `rec_city_nm = '上海'` | 库内为 `'上海市'`（见 `common_values.md`） |
| 时间字段 | `trans_dt = '20250101'` 或误用 `rec_dt` | `t.trans_dt >= '2025-01-01' AND t.trans_dt <= '2025-12-31'` |
| 活动 / 品类 | 活动名、品类值拼错或多余空格 | 对照 `common_values.md` 精确匹配 |
| 分公司名 | `LIKE '%上海%'` 或 `'上海'` | `branch_org_nm = 'XX分公司'` 精确等于 |
| 日期范围过窄 | 月份、scope 与 reporter 不一致 | 核对 query_xx 起止 `trans_dt`（`'YYYY-MM-DD'`） |

不确定取值时，可对可疑字段做 `SELECT DISTINCT col ... LIMIT 20` 核对（仍须 checker → query）。

### 2. 检查 JOIN 与关联条件

| 排查项 | 常见错误 | 正确做法 |
|--------|----------|----------|
| 缺 JOIN | 要用 `branch_org_nm` 但未 JOIN `usr_dim` | `JOIN usr_dim u ON t.usr_id = u.usr_id` |
| 关联键错误 | `ON t.mchnt_cd = u.usr_id` 等张冠李戴 | 事实表 `usr_id` 对 `usr_dim.usr_id`；商户对 `mchnt_dim.mchnt_cd` |
| 多余 INNER JOIN | 不必要的 JOIN 把事实表行全部滤掉 | 去掉无关 JOIN，或改 LEFT JOIN 验证 |
| 表别名 | WHERE 用了 `u.xxx` 但未 JOIN `u` | 别名与 FROM/JOIN 一致 |

### 3. 重试流程

```
0 行 → 列出可能误写点（WHERE 取值 / JOIN / 时间口径）
     → 对照 common_values.md 修正 SQL
     → sql_db_query_checker → sql_db_query 再查
     → 仍 0 行且为关键指标 → 才可回复「暂无相关数据」
```

## 规则

1. 仅 SELECT；禁止 DML/DDL
2. SQL 先 checker 再 query
3. 只查相关列；大结果在 SQL 内聚合
4. 禁止臆造 query 未返回的数据
5. **`row_count=0` 时必做 WHERE / JOIN 校验并重试**（见上文「0 行结果：必做校验」），不可一次 0 行就结束或填「暂无数据」
