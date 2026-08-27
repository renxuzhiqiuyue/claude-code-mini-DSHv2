---
name: local-chart
description: 当以旧换新月报需要生成业务图表时使用本 Skill。读取 data/query_xx.json，按分析目的生成饼图（占比）、折线图（趋势对比）、柱形图（项间对比），输出 PNG 并嵌入 report.md。须在 SQL 数据落盘且 report.md 已写入占位符后调用。
---

# 本地 Python 出图 Skill

## 概述

本 Skill 配合 **yijiu-huanxin-reporter**：在 `data/query_xx.json` 落盘后，用本地 Python + matplotlib 生成图表 PNG，并自动将 `【图：…】` 占位符替换为 Markdown 图片引用。图表数据只能来自已缓存的 query JSON，禁止手写数字。

## 工作区与路径约定

- cwd = `OUTPUT_DIR`（默认 `.output/`，工具沙箱根）
- 数据：`data/`；报告：`report.md`；图表：`images/`
- 出图：`python ../skills/solver/local_chart/scripts/generate_charts.py --run-dir .`

## 核心能力

- 从 `data/query_xx.json` 读取业务数据并生成 chart_1/2/3 PNG
- 按强制选型规则匹配饼图、折线图、柱形图，禁止错配
- 自动嵌入 `report.md`（替换占位符或按规则插入）
- 支持中文字体（内置 fonts/、系统 Noto、Windows 雅黑等）
- 支持 `--only` 单独生成指定图表

## 何时使用

**必须加载本 Skill 当：**

- outline / reporter 框架中含 `【图：…】` 占位符
- `data/query_02` / `query_03` / `query_05` 等数据已写入
- `report.md` 已存在（含占位符或正文）
- 需要执行 `bash` 调用出图脚本

**不要用于：** 根因决策树（见 root-cause-tracer）、手写数字凑图、无 query 文件时伪造 PNG。

## 工作流程

### 步骤 1：确认前置条件

- 已 `load_skill(yijiu-huanxin-reporter)` 且框架含图表占位
- 已 `load_skill(read-sql-data)` 并完成对应 query_xx 缓存
- **`query_05.json` 已写入且 `rows[].age_group` 存在**（年龄数据；**不是** query_04 性别）
- `report.md` 已 `write_file`（含 `【图：…】`）

### 步骤 2：执行出图命令

在 **OUTPUT_DIR**（默认 `.output/`）下执行：

```bash
python ../skills/solver/local_chart/scripts/generate_charts.py --run-dir .
```

仅生成 chart_2：

```bash
python ../skills/solver/local_chart/scripts/generate_charts.py --run-dir . --only chart_2
```

### 步骤 3：检查输出

脚本 stdout 打印 JSON，含 `generated`、`embedded_in_md`、`report_md`。确认 PNG 已生成且 report.md 已嵌入引用。

### 步骤 4：补写图前图后解读

出图成功后，Agent 仍须在 report.md 中保留或补写图前/图后分析句（见 yijiu-huanxin-reporter「正文深度写作规范」）。

---

## 环境与依赖

依赖：`matplotlib`（当前 shell 的 `python` 即可；需已安装 matplotlib）。

### 中文字体

脚本按顺序选字体：Skill 内置 `skills/solver/local_chart/fonts/` → 系统 Noto / 文泉驿 → Windows 雅黑。Linux 可 `sudo apt install fonts-noto-cjk`，或将 `.otf`/`.ttf` 放入 `skills/solver/local_chart/fonts/`。

---

## 图表选型规则（强制）

| 分析目的 | 图表类型 | 典型场景 | 映射 |
|----------|----------|----------|------|
| 占比 / 构成 / 结构 | **饼图** | 各品类金额占比 | `chart_1` ← `query_02` |
| 时间趋势 / 两期对比 | **折线图** | 环比、当期 vs 基期 | `chart_3` ← `query_02` + `query_03` |
| 各数据项横向对比 | **柱形图** | 年龄段、城市等 | `chart_2` ← `query_05` |

**禁止错配：** 占比不得用柱/折线替代；趋势不得用柱形替代（离散项对比除外）；项间对比不得用饼/折线替代。

---

## 图表与数据来源

| 文件 | 类型 | 数据来源 |
|------|------|----------|
| `chart_1.png` | 饼图 | `query_02.json` → `rows[].prod_tp`, `trans_amt`/`amt` |
| `chart_2.png` | 柱形图 | **`query_05.json`** → **`rows[].age_group`**, `trans_amt`/`amt` |

**query_05 校验（出 chart_2 前必做）：**

| 检查项 | 通过 | 失败时的含义 |
|--------|------|--------------|
| 文件存在 | `data/query_05.json` | 须先按 read-sql-data 写年龄 SQL |
| 字段名 | `rows[0]` 含 **`age_group`** | 若只有 `sex`，说明年龄/性别 **query 编号写反** |
| 行数 | ≥ 2 个年龄段 | 空 rows 则跳过 chart_2 |

**错误示例（会导致 chart_2 标签全为「未知」）：**

```json
{"rows": [{"sex": "男", "trans_amt": 882252.85}, {"sex": "女", "trans_amt": 834358.55}]}
```

**正确示例：**

```json
{"rows": [{"age_group": "40-49岁", "trans_amt": 370807.35}, {"age_group": "60岁及以上", "trans_amt": 359689.11}]}
```

若年龄数据误写在 `query_04.json`，须 **重新执行年龄 SQL 并 write_file 到 query_05.json**，不要改出图脚本。
| `chart_3.png` | 折线图 | `query_02.json` + `query_03.json` |

| 条件 | 动作 |
|------|------|
| 有 `query_02` | 生成 chart_1 |
| 有 `query_05` | 生成 chart_2 |
| 有 `query_02` + `query_03` | 生成 chart_3 |
| 无对应 query | 跳过该图 |

---

## 输出与嵌入

| 文件 | Markdown 引用示例 |
|------|---------------------|
| `images/chart_1.png` | `![各品类交易金额占比](images/chart_1.png)` |
| `images/chart_2.png` | `![用户年龄分布](images/chart_2.png)` |
| `images/chart_3.png` | `![各品类交易金额环比对比](images/chart_3.png)` |

若无 `【图：…】` 占位符，脚本按内置规则插入（如 chart_2 插在「用户城市分布」节前）。

---

## 规则

1. **禁止** 不读 query JSON 手动画图或伪造 PNG
2. **禁止** 修改 `generate_charts.py` 内聚合逻辑；缺字段时改 SQL 重跑
3. 命令须在 **OUTPUT_DIR** 下执行，使用 `python ../skills/solver/local_chart/scripts/generate_charts.py`
4. **禁止** 只生成 PNG 却不更新 report.md（除非 `--no-embed-md`）

---

## 故障排查

| 现象 | 处理 |
|------|------|
| 找不到 query_02 | 先完成 read-sql-data 写 query_02 |
| chart_2 缺少 data | 写 **query_05**（**年龄**；`age_group` 字段） |
| chart_2 标签全为「未知」 | **query_05 写成了性别数据**；年龄改存 query_05，性别改存 query_04（见 reporter / read-sql-data 固定编号表） |
| 年龄在 query_04、性别在 query_05 | **编号颠倒**；按 Skill 固定编号重跑 SQL 并覆盖 JSON |
| 中文乱码 | 安装 fonts-noto-cjk 或放入 `fonts/` |
| matplotlib 未安装 | `python -m pip install matplotlib` |
