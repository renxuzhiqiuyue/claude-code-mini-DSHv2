# -*- coding: utf-8 -*-
"""Root cause tracer CLI — delegates to tools.root_cause_utils."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools import root_cause_utils as rc  # noqa: E402


def load_csv(file_path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    path = Path(file_path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV 文件为空或缺少表头")
        rows = [dict(row) for row in reader]
        return list(reader.fieldnames), rows


def validate_csv(
    file_path: str | Path,
    period_col: str,
    metrics: list[str],
    dimensions: list[str],
    current_label: str = "当期",
    base_label: str = "基期",
) -> dict[str, Any]:
    columns, rows = load_csv(file_path)
    if not metrics:
        return {"valid": False, "errors": ["metrics 不能为空"], "row_count": 0, "columns": columns}
    validation = rc.validate_rows(
        columns, rows, period_col, metrics[0], dimensions, current_label, base_label
    )
    for metric in metrics[1:]:
        if metric not in columns:
            validation["valid"] = False
            validation.setdefault("errors", []).append(f"列不存在: {metric}")
    return validation


def drill_down(
    file_path: str | Path,
    metrics: list[str],
    dimensions: list[str],
    period_col: str,
    current_label: str = "当期",
    base_label: str = "基期",
    cum_threshold: float = 0.6,
) -> dict[str, Any]:
    validation = validate_csv(
        file_path, period_col, metrics, dimensions, current_label, base_label
    )
    if not validation["valid"]:
        return {"success": False, "validation": validation, "results": []}

    _, rows = load_csv(file_path)
    results: list[dict[str, Any]] = []

    for metric in metrics:
        result = rc.build_root_cause_drill(
            rows,
            metric,
            dimensions,
            period_col,
            current_label,
            base_label,
            cum_threshold,
        )
        if not result.get("success"):
            return {"success": False, "validation": result.get("validation", validation), "results": []}
        results.append(
            {
                "metric": metric,
                "overall": result["overall"],
                "drill_path": result["drill_path"],
                "tree": result.get("tree", {}),
            }
        )

    return {"success": True, "validation": validation, "results": results}


def format_report(result: dict[str, Any]) -> str:
    if not result.get("success"):
        errors = result.get("validation", {}).get("errors", ["未知错误"])
        return "校验失败:\n" + "\n".join(f"- {err}" for err in errors)

    lines: list[str] = ["# 指标根因溯源报告", ""]
    for metric_result in result["results"]:
        wrapped = {
            "success": True,
            "metric": metric_result["metric"],
            "overall": metric_result["overall"],
            "drill_path": metric_result["drill_path"],
        }
        lines.append(rc.format_tree_report(wrapped).replace("# 指标根因溯源报告\n\n", "", 1))
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Root cause tracer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate CSV input")
    validate_parser.add_argument("file_path")
    validate_parser.add_argument("--period-col", required=True)
    validate_parser.add_argument("--metrics", required=True, help="Comma-separated")
    validate_parser.add_argument("--dimensions", required=True, help="Comma-separated")
    validate_parser.add_argument("--current-label", default="当期")
    validate_parser.add_argument("--base-label", default="基期")

    drill_parser = subparsers.add_parser("drill", help="Run drill-down analysis")
    drill_parser.add_argument("file_path")
    drill_parser.add_argument("--period-col", required=True)
    drill_parser.add_argument("--metrics", required=True, help="Comma-separated")
    drill_parser.add_argument("--dimensions", required=True, help="Comma-separated")
    drill_parser.add_argument("--current-label", default="当期")
    drill_parser.add_argument("--base-label", default="基期")
    drill_parser.add_argument("--cum-threshold", type=float, default=0.6)
    drill_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="markdown",
        help="Output format",
    )

    args = parser.parse_args()
    metrics = [item.strip() for item in args.metrics.split(",") if item.strip()]
    dimensions = [item.strip() for item in args.dimensions.split(",") if item.strip()]

    if args.command == "validate":
        output = validate_csv(
            args.file_path,
            args.period_col,
            metrics,
            dimensions,
            args.current_label,
            args.base_label,
        )
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    result = drill_down(
        args.file_path,
        metrics,
        dimensions,
        args.period_col,
        args.current_label,
        args.base_label,
        args.cum_threshold,
    )

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))


if __name__ == "__main__":
    main()
