---
name: chart-plotting
description: 用 Python/matplotlib 绘制折线图、柱状图、饼图等数据可视化，输出 PNG/SVG 到 OUTPUT_DIR/charts/。在用户要求画图、做图表、数据可视化、趋势对比或占比展示时使用。
---

# 数据可视化 / 画图 Skill

你具备用 **Python + matplotlib** 绘制常见统计图表的能力。图表用于展示数据趋势、对比与占比，**不是** UI 设计稿或艺术插画。

## 工作区与路径约定

- Agent 当前工作区：`OUTPUT_DIR`（默认 `.output/`）
- 通用图表输出：`charts/`（相对 OUTPUT_DIR）
- 以旧换新月报业务图见 `local-chart`（`images/`）

## 何时使用

- 用户要求「画折线图 / 柱状图 / 饼图 / 图表 / 可视化」
- 已有 CSV、表格或数字列表，需要生成图片交付
- 需要在报告中插入趋势图、对比图、占比图

## 不适用

- 复杂交互式 Dashboard（除非用户明确要求 Plotly）
- 3D 建模、流程图、架构图（用 Mermaid 或 draw.io 更合适）
- 无数据凭空虚构曲线（须基于用户数据或可验证来源）

## 依赖

```bash
pip install matplotlib
# 可选：pip install pandas   # 读 CSV 更方便
```

项目 `requirements.txt` 已含 matplotlib 时直接 import；若报错再 `pip install`。

## 输出约定

| 项 | 规则 |
|----|------|
| 目录 | `charts/`（相对 OUTPUT_DIR；勿逃逸沙箱） |
| 格式 | 默认 **PNG**（`dpi=150`）；用户要矢量时用 **SVG** |
| 命名 | `{主题}-{图表类型}.png`，如 `sales-2024-line.png` |
| 脚本 | 可写 `charts/plot_<主题>.py`，执行后保留图片与脚本 |

生成后用 `bash` 运行脚本，确认文件存在并告知用户完整路径。

## 执行流程

### 1. 确认数据与图表类型

向用户确认（若未说明）：

| 项 | 说明 |
|----|------|
| 数据 | 内联数字 / CSV 路径 / 需从文件读取 |
| 图表 | 折线 / 柱状 / 饼图 / 组合（如双轴折线） |
| 标题与轴标签 | 中文或英文 |
| 输出文件名 | 默认按主题自动生成 |

**选型建议**

| 目的 | 推荐 |
|------|------|
| 时间趋势、连续变化 | 折线图 |
| 类别对比、排名 | 柱状图（横向适合长标签） |
| 部分占整体比例 | 饼图（类别 ≤7；过多用柱状图） |
| 多系列趋势 | 多条折线或分组柱状图 |

### 2. 准备数据

- 优先 `read_file` 读取用户 CSV/JSON
- 小数据集可直接在脚本内用 `dict` / `list`
- 缺失值、非数字须清洗后再画

### 3. 编写并运行脚本

统一模板（复制后按图表类型改）：

```python
"""生成图表 — 由 Agent 写入 charts/ 后 bash 执行。"""
from pathlib import Path

import matplotlib.pyplot as plt

OUT_DIR = Path("charts")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 中文标签：优先系统常见 CJK 字体，避免 DejaVu 缺字警告
plt.rcParams["font.sans-serif"] = [
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "SimHei",
    "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

# ── 在此填入数据 ──
# ...
```

执行：

```bash
python charts/plot_<主题>.py
ls -la charts/
```

---

## 折线图（Line Chart）

适用：日期/月份/序号 vs 数值，展示趋势。

```python
from pathlib import Path
import matplotlib.pyplot as plt

OUT = Path("charts/trend-line.png")
OUT.parent.mkdir(parents=True, exist_ok=True)

x = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
y = [12, 19, 15, 22, 28, 24]

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(x, y, marker="o", linewidth=2, color="#2563eb")
ax.set_title("Monthly Active Users")
ax.set_xlabel("Month")
ax.set_ylabel("Count")
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(OUT, dpi=150)
plt.close()
print(f"Saved {OUT}")
```

**多系列折线**：对每条系列调用 `ax.plot(..., label=name)`，最后 `ax.legend()`。

---

## 柱状图（Bar Chart）

适用：离散类别对比。

**纵向柱状图**

```python
from pathlib import Path
import matplotlib.pyplot as plt

OUT = Path("charts/category-bar.png")
OUT.parent.mkdir(parents=True, exist_ok=True)

categories = ["Product A", "Product B", "Product C", "Product D"]
values = [45, 72, 38, 91]

fig, ax = plt.subplots(figsize=(8, 4.5))
bars = ax.bar(categories, values, color="#059669", edgecolor="white", width=0.6)
ax.set_title("Sales by Product")
ax.set_ylabel("Revenue (k)")
ax.bar_label(bars, fmt="%.0f", padding=3)
fig.tight_layout()
fig.savefig(OUT, dpi=150)
plt.close()
```

**横向柱状图**（类别名很长）：`ax.barh(categories, values)`

**分组柱状图**：`x = range(len(cats))`; `ax.bar(x - w/2, v1, width=w)` 与 `ax.bar(x + w/2, v2, width=w)`；`ax.set_xticks(x); ax.set_xticklabels(cats)`

---

## 饼图（Pie Chart）

适用：占比总和为 100%（或自动 normalize）。类别不宜过多。

```python
from pathlib import Path
import matplotlib.pyplot as plt

OUT = Path("charts/share-pie.png")
OUT.parent.mkdir(parents=True, exist_ok=True)

labels = ["Backend", "Frontend", "DevOps", "QA", "Other"]
sizes = [35, 28, 15, 12, 10]
colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"]
explode = (0.02,) * len(labels)  # 可选：略分离

fig, ax = plt.subplots(figsize=(7, 7))
ax.pie(
    sizes,
    labels=labels,
    autopct="%1.1f%%",
    startangle=90,
    colors=colors,
    explode=explode,
    pctdistance=0.75,
)
ax.set_title("Effort Distribution")
ax.axis("equal")
fig.tight_layout()
fig.savefig(OUT, dpi=150)
plt.close()
```

**注意**：负值、全零数据不能画饼图；多项总和明显不等于 100% 时在标题或图注说明。

---

## 从 CSV 读取（可选）

```python
import csv
from pathlib import Path
import matplotlib.pyplot as plt

csv_path = Path("charts/data/metrics.csv")  # 用户指定路径（相对 OUTPUT_DIR）
rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
x = [r["month"] for r in rows]
y = [float(r["value"]) for r in rows]
# 再接折线或柱状模板
```

有 pandas 时：`df = pd.read_csv(...); df.plot(kind="bar", x="cat", y="val")`

---

## 质量检查清单

- [ ] 标题、轴标签、图例清晰
- [ ] 数据与用户提供一致（不捏造）
- [ ] 图片已保存到 `charts/`
- [ ] 脚本可重复运行（`mkdir`、关闭 figure：`plt.close()`）
- [ ] 中文乱码时：改英文标签，或说明需安装中文字体
- [ ] 向用户报告：**文件路径** + 图表类型 + 数据摘要

## 交付话术示例

> 已生成折线图 `charts/sales-2024-line.png`，展示 1–6 月活跃用户趋势。脚本位于 `charts/plot_sales.py`，可修改数据后重新运行。
