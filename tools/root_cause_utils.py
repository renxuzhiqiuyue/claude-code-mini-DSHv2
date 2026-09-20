# -*- coding: utf-8 -*-
"""根因下钻算法（tools/root_cause.py 的附属实现）。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from harness.config import OUTPUT_DIR


def _cache_dir() -> Path:
    """大数据集缓存目录：OUTPUT_DIR/cache。"""
    return Path(OUTPUT_DIR) / "cache"


INLINE_ROW_LIMIT = 500
MAX_DRILL_LAYERS = 2
MAX_NAMED_VALUES = 5
OTHER_LABEL = "其他"


def _resolve_drill_layer_count(dimensions: list[str]) -> int:
    """Fixed drill depth: 2 layers when dimensions >= 2, else len(dimensions). Never > 2."""
    if len(dimensions) >= MAX_DRILL_LAYERS:
        return MAX_DRILL_LAYERS
    return len(dimensions)


def save_dataset(payload: dict[str, Any]) -> str:
    _cache_dir().mkdir(parents=True, exist_ok=True)
    cache_id = f"{uuid.uuid4().hex}.json"
    target = _cache_dir() / cache_id
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache_id


def load_dataset(cache_id: str) -> dict[str, Any]:
    if "/" in cache_id or "\\" in cache_id or ".." in cache_id:
        raise ValueError("非法 cache_id")

    target = (_cache_dir() / cache_id).resolve()
    if not str(target).startswith(str(_cache_dir().resolve())):
        raise ValueError("非法 cache_id 路径")

    if not target.exists():
        raise FileNotFoundError(f"缓存不存在: {cache_id}")

    return json.loads(target.read_text(encoding="utf-8"))


def normalize_rows(rows: list[dict]) -> list[dict[str, str]]:
    """Convert SQLite query rows to string-keyed dicts for analysis."""
    return [{str(k): "" if v is None else str(v) for k, v in row.items()} for row in rows]


def validate_rows(
    columns: list[str],
    rows: list[dict],
    period_col: str,
    metric: str,
    dimensions: list[str],
    current_label: str = "当期",
    base_label: str = "基期",
) -> dict[str, Any]:
    errors: list[str] = []

    for col in [period_col, metric, *dimensions]:
        if col not in columns:
            errors.append(f"列不存在: {col}")

    period_values: list[str] = []
    if period_col in columns:
        period_values = sorted({str(row.get(period_col, "")) for row in rows})
        if current_label not in period_values:
            errors.append(f"周期列中未找到当期标签: {current_label}")
        if base_label not in period_values:
            errors.append(f"周期列中未找到基期标签: {base_label}")

    if metric in columns:
        for row in rows[:100]:
            raw = row.get(metric, "")
            if raw != "":
                try:
                    float(raw)
                except (TypeError, ValueError):
                    errors.append(f"指标列非数值类型: {metric}")
                    break

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "row_count": len(rows),
        "columns": columns,
        "period_values": period_values,
    }


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sum_metric(
    rows: list[dict[str, str]],
    metric: str,
    period_col: str,
    period_label: str,
    dim: str | None = None,
    dim_value: str | None = None,
) -> float:
    total = 0.0
    for row in rows:
        if str(row.get(period_col, "")) != period_label:
            continue
        if dim is not None and str(row.get(dim, "")) != dim_value:
            continue
        total += _to_float(row.get(metric, "0"))
    return total


def _compute_dimension_deltas(
    rows: list[dict[str, str]],
    metric: str,
    dim: str,
    period_col: str,
    current_label: str,
    base_label: str,
) -> list[dict[str, Any]]:
    values = {str(row.get(dim, "")) for row in rows}
    result: list[dict[str, Any]] = []
    for value in values:
        current = _sum_metric(rows, metric, period_col, current_label, dim, value)
        base = _sum_metric(rows, metric, period_col, base_label, dim, value)
        result.append(
            {
                "value": value,
                "current": current,
                "base": base,
                "delta": current - base,
            }
        )
    return result


def _dimension_score(deltas: list[dict[str, Any]], direction: str) -> float:
    if direction == "down":
        return sum(item["delta"] for item in deltas if item["delta"] < 0)
    if direction == "up":
        return sum(item["delta"] for item in deltas if item["delta"] > 0)
    return 0.0


def _same_direction_candidates(
    deltas: list[dict[str, Any]], direction: str
) -> list[dict[str, Any]]:
    if direction == "down":
        items = [dict(item) for item in deltas if item["delta"] < 0]
        return sorted(items, key=lambda item: item["delta"])
    if direction == "up":
        items = [dict(item) for item in deltas if item["delta"] > 0]
        return sorted(items, key=lambda item: -item["delta"])
    return []


def _prepare_display_values(
    deltas: list[dict[str, Any]],
    delta_total: float,
    direction: str,
    max_named: int = MAX_NAMED_VALUES,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Top N named values + optional 「其他」; drill_filter excludes 「其他」."""
    candidates = _same_direction_candidates(deltas, direction)
    if not candidates:
        candidates = sorted(
            [dict(item) for item in deltas],
            key=lambda item: -abs(item["delta"]),
        )

    display: list[dict[str, Any]] = []
    drill_filter: list[str] = []

    def _with_rate(item: dict[str, Any], is_other: bool, merged_count: int = 0) -> dict[str, Any]:
        entry = dict(item)
        entry["is_other"] = is_other
        entry["contribution_rate"] = (
            round(entry["delta"] / delta_total, 4) if delta_total != 0 else 0
        )
        if merged_count:
            entry["merged_count"] = merged_count
        return entry

    if len(candidates) <= max_named:
        for item in candidates:
            display.append(_with_rate(item, False))
            drill_filter.append(str(item["value"]))
        return display, drill_filter

    top = candidates[:max_named]
    rest = candidates[max_named:]
    for item in top:
        display.append(_with_rate(item, False))
        drill_filter.append(str(item["value"]))

    other = {
        "value": OTHER_LABEL,
        "current": sum(r["current"] for r in rest),
        "base": sum(r["base"] for r in rest),
        "delta": sum(r["delta"] for r in rest),
    }
    display.append(_with_rate(other, True, merged_count=len(rest)))
    return display, drill_filter


def _select_by_cumulative_threshold(
    deltas: list[dict[str, Any]],
    delta_total: float,
    direction: str,
    threshold: float = 0.6,
) -> list[dict[str, Any]]:
    if delta_total == 0:
        return []

    if direction == "down":
        candidates = sorted(
            [item for item in deltas if item["delta"] < 0],
            key=lambda item: item["delta"],
        )
    elif direction == "up":
        candidates = sorted(
            [item for item in deltas if item["delta"] > 0],
            key=lambda item: -item["delta"],
        )
    else:
        return []

    if not candidates:
        return []

    total_abs = abs(delta_total)
    selected: list[dict[str, Any]] = []
    cumulative = 0.0

    for item in candidates:
        selected.append(dict(item))
        cumulative += abs(item["delta"])
        if cumulative / total_abs >= threshold:
            break

    return selected


def _metric_direction(delta_total: float) -> str:
    if delta_total < 0:
        return "down"
    if delta_total > 0:
        return "up"
    return "flat"


def _overall_stats(
    rows: list[dict[str, str]],
    metric: str,
    period_col: str,
    current_label: str,
    base_label: str,
) -> dict[str, Any]:
    current_total = _sum_metric(rows, metric, period_col, current_label)
    base_total = _sum_metric(rows, metric, period_col, base_label)
    delta_total = current_total - base_total
    return {
        "current": current_total,
        "base": base_total,
        "delta": delta_total,
        "rate": round(delta_total / base_total, 4) if base_total != 0 else None,
        "direction": _metric_direction(delta_total),
    }


def _filter_rows(
    rows: list[dict[str, str]], dim: str, selected_values: list[str]
) -> list[dict[str, str]]:
    allowed = set(selected_values)
    return [row for row in rows if str(row.get(dim, "")) in allowed]


def _pick_best_dimension(
    dim_scores: dict[str, float], direction: str
) -> str:
    if direction == "down":
        return min(dim_scores, key=dim_scores.get)
    return max(dim_scores, key=dim_scores.get)


def _fmt_delta_short(value: float) -> str:
    sign = "+" if value >= 0 else ""
    if abs(value) >= 10000:
        return f"{sign}{value / 10000:.2f}万"
    return f"{sign}{value:.0f}"


def build_tree_graph(
    metric: str,
    overall: dict[str, Any],
    drill_path: list[dict[str, Any]],
) -> dict[str, Any]:
    """Decision tree: L1 values fan out; non-「其他」 converge, then L2 dimension."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    counter = 0

    def _add_node(label: str, kind: str, rank: int = 0) -> str:
        nonlocal counter
        node_id = f"n{counter}"
        counter += 1
        nodes.append({"id": node_id, "label": label, "kind": kind, "rank": rank})
        return node_id

    root_id = _add_node(
        f"{metric}\nΔ={_fmt_delta_short(overall['delta'])}",
        "root",
        rank=0,
    )

    if not drill_path:
        return {"nodes": nodes, "edges": edges}

    l1 = drill_path[0]
    d1_id = _add_node(
        f"{l1['dimension']}\n解释力 {l1['dimension_score']}",
        "dimension",
        rank=1,
    )
    edges.append({"from": root_id, "to": d1_id})

    non_other_value_ids: list[str] = []
    display_l1 = l1.get("display_values") or l1.get("selected_values", [])
    for item in display_l1:
        label = f"{item['value']}\nΔ={_fmt_delta_short(item['delta'])}"
        rate = item.get("contribution_rate")
        if rate is not None:
            label += f"\n{rate * 100:.1f}%"
        is_other = item.get("is_other", False)
        val_id = _add_node(label, "other" if is_other else "value", rank=2)
        edges.append({"from": d1_id, "to": val_id})
        if not is_other:
            non_other_value_ids.append(val_id)

    if len(drill_path) > 1 and non_other_value_ids:
        merge_id = _add_node("非「其他」\n汇合下钻", "merge", rank=3)
        for val_id in non_other_value_ids:
            edges.append({"from": val_id, "to": merge_id})

        l2 = drill_path[1]
        d2_id = _add_node(
            f"{l2['dimension']}\n解释力 {l2['dimension_score']}",
            "dimension",
            rank=4,
        )
        edges.append({"from": merge_id, "to": d2_id})

        display_l2 = l2.get("display_values") or l2.get("selected_values", [])
        for item in display_l2:
            label = f"{item['value']}\nΔ={_fmt_delta_short(item['delta'])}"
            rate = item.get("contribution_rate")
            if rate is not None:
                label += f"\n{rate * 100:.1f}%"
            kind = "other" if item.get("is_other") else "value"
            val_id = _add_node(label, kind, rank=5)
            edges.append({"from": d2_id, "to": val_id})

    return {"nodes": nodes, "edges": edges}


def _drill_layers(
    rows: list[dict[str, str]],
    metric: str,
    dimensions: list[str],
    period_col: str,
    current_label: str,
    base_label: str,
    cum_threshold: float,
) -> list[dict[str, Any]]:
    """Drill exactly up to MAX_DRILL_LAYERS (2); 5+其他展示；第2层排除「其他」."""
    overall = _overall_stats(rows, metric, period_col, current_label, base_label)
    delta_total = overall["delta"]
    direction = overall["direction"]

    if direction == "flat" or not dimensions:
        return []

    target_layers = _resolve_drill_layer_count(dimensions)

    remaining_dims = list(dimensions)
    filtered_rows = rows
    drill_path: list[dict[str, Any]] = []

    for _ in range(target_layers):
        if not remaining_dims:
            break

        dim_scores: dict[str, float] = {}
        dim_deltas_map: dict[str, list[dict[str, Any]]] = {}

        for dim in remaining_dims:
            deltas = _compute_dimension_deltas(
                filtered_rows, metric, dim, period_col, current_label, base_label
            )
            dim_deltas_map[dim] = deltas
            dim_scores[dim] = _dimension_score(deltas, direction)

        best_dim = _pick_best_dimension(dim_scores, direction)
        display_values, drill_filter = _prepare_display_values(
            dim_deltas_map[best_dim], delta_total, direction
        )

        if drill_filter:
            filtered_rows = _filter_rows(filtered_rows, best_dim, drill_filter)

        drill_path.append(
            {
                "step": len(drill_path) + 1,
                "dimension": best_dim,
                "dimension_score": round(dim_scores[best_dim], 4),
                "all_dimension_scores": {
                    dim: round(score, 4) for dim, score in dim_scores.items()
                },
                "display_values": display_values,
                "drill_filter_values": drill_filter,
                "selected_values": display_values,
                "remaining_rows": len(filtered_rows),
            }
        )
        remaining_dims.remove(best_dim)

    return drill_path


def _drill_one_dimension(
    rows: list[dict[str, str]],
    metric: str,
    dimensions: list[str],
    period_col: str,
    current_label: str,
    base_label: str,
    cum_threshold: float,
) -> dict[str, Any] | None:
    """Return first drill layer (backward compatible)."""
    path = _drill_layers(
        rows, metric, dimensions, period_col, current_label, base_label, cum_threshold
    )
    return path[0] if path else None


def build_root_cause_drill(
    rows: list[dict[str, str]],
    metric: str,
    dimensions: list[str],
    period_col: str,
    current_label: str = "当期",
    base_label: str = "基期",
    cum_threshold: float = 0.6,
) -> dict[str, Any]:
    """
    单指标、多维度：固定下钻 2 层（dimensions ≥ 2 时），不得超过 2 层。
    每一层输出全部候选维度的解释力得分，并标注选中维度。
    """
    columns = list(rows[0].keys()) if rows else []
    validation = validate_rows(
        columns, rows, period_col, metric, dimensions, current_label, base_label
    )
    if not validation["valid"]:
        return {"success": False, "validation": validation}

    overall = _overall_stats(rows, metric, period_col, current_label, base_label)
    drill_path = _drill_layers(
        rows,
        metric,
        dimensions,
        period_col,
        current_label,
        base_label,
        cum_threshold,
    )
    drill = drill_path[0] if drill_path else None
    tree = build_tree_graph(metric, overall, drill_path) if drill_path else {"nodes": [], "edges": []}

    return {
        "success": True,
        "validation": validation,
        "metric": metric,
        "overall": overall,
        "drill": drill,
        "drill_path": drill_path,
        "tree": tree,
    }


def build_root_cause_tree_rows(
    rows: list[dict[str, str]],
    metric: str,
    dimensions: list[str],
    period_col: str,
    current_label: str = "当期",
    base_label: str = "基期",
    cum_threshold: float = 0.6,
) -> dict[str, Any]:
    """Alias for build_root_cause_drill."""
    return build_root_cause_drill(
        rows,
        metric,
        dimensions,
        period_col,
        current_label,
        base_label,
        cum_threshold,
    )


def _format_dimension_scores_table(all_scores: dict[str, float], selected_dim: str) -> list[str]:
    lines = [
        "**各维度解释力得分**（选中维度加粗）：",
        "",
        "| 维度 | 解释力得分 |",
        "|------|-----------|",
    ]
    for dim, score in sorted(all_scores.items(), key=lambda item: -abs(item[1])):
        label = f"**{dim}**" if dim == selected_dim else dim
        lines.append(f"| {label} | {score} |")
    lines.append("")
    return lines


def format_tree_report(result: dict[str, Any]) -> str:
    if not result.get("success"):
        errors = result.get("validation", {}).get("errors", ["未知错误"])
        return "校验失败:\n" + "\n".join(f"- {err}" for err in errors)

    lines: list[str] = ["# 指标根因溯源报告", ""]
    direction_map = {"down": "下降", "up": "上升", "flat": "持平"}

    overall = result["overall"]
    metric = result["metric"]
    lines.extend(
        [
            f"## 指标: {metric}",
            "",
            f"- 当期: {overall['current']}",
            f"- 基期: {overall['base']}",
            f"- 变化量: {overall['delta']}",
            f"- 环比: {overall['rate']}",
            f"- 方向: {direction_map[overall['direction']]}",
            "",
        ]
    )

    if overall["direction"] == "flat":
        lines.extend(["指标无变化，无需下钻。", ""])
        return "\n".join(lines)

    drill_path = result.get("drill_path") or []
    if not drill_path and result.get("drill"):
        drill_path = [result["drill"]]

    if not drill_path:
        lines.extend(["未找到可下钻维度。", ""])
        return "\n".join(lines)

    lines.extend(["### 下钻路径", ""])
    for step in drill_path:
        step_no = step.get("step", drill_path.index(step) + 1)
        selected_dim = step["dimension"]
        lines.append(f"**第 {step_no} 层 — 主因维度 `{selected_dim}`**")
        lines.append(f"（该维度解释力得分: {step['dimension_score']}）")
        lines.append("")
        all_scores = step.get("all_dimension_scores")
        if all_scores:
            lines.extend(_format_dimension_scores_table(all_scores, selected_dim))
        lines.extend(
            [
                "| 取值 | 当期 | 基期 | 变化量 | 贡献率 |",
                "|------|------|------|--------|--------|",
            ]
        )
        for item in step.get("display_values") or step.get("selected_values", []):
            rate_pct = f"{item['contribution_rate'] * 100:.1f}%"
            value_label = item["value"]
            if item.get("is_other") and item.get("merged_count"):
                value_label = f"{value_label}（合并 {item['merged_count']} 项）"
            lines.append(
                f"| {value_label} | {item['current']} | {item['base']} | "
                f"{item['delta']} | {rate_pct} |"
            )
        lines.append("")
        if step.get("step") == 1 and len(drill_path) > 1:
            lines.append("> 第 2 层在排除「其他」后的子集上全局下钻。")
            lines.append("")
        if "remaining_rows" in step:
            lines.append(f"过滤后剩余行数: {step['remaining_rows']}")
            lines.append("")

    return "\n".join(lines)
