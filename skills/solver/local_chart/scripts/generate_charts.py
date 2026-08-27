"""Generate report charts from cached query_xx.json files.

图表选型规则（Agent / 脚本均须遵守）：
- 占比、构成、结构 → 饼图（pie）
- 时间趋势、两期/多期对比趋势 → 折线图（line）
- 各数据项之间横向对比（品类、年龄段、城市等）→ 柱形图（bar）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _worktree_root() -> Path:
    """Agent bash cwd: OUTPUT_DIR（默认 .output）。"""
    return Path.cwd().resolve()


def _skill_fonts_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "fonts"


def _register_font_file(path: Path) -> str | None:
    import matplotlib.font_manager as fm

    try:
        fm.fontManager.addfont(str(path))
        return fm.FontProperties(fname=str(path)).get_name()
    except Exception:
        return None


def _resolve_cjk_font() -> str | None:
    """Pick a CJK-capable font: bundled → system files → cached font list."""
    import matplotlib.font_manager as fm

    bundled = _skill_fonts_dir()
    for pattern in ("NotoSansSC-Regular.otf", "NotoSansCJKsc-Regular.otf", "*.otf", "*.ttf", "*.ttc"):
        for path in sorted(bundled.glob(pattern)):
            name = _register_font_file(path)
            if name:
                return name

    system_candidates = (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf"),
    )
    for path in system_candidates:
        if path.is_file():
            name = _register_font_file(path)
            if name:
                return name

    preferred = (
        "Noto Sans CJK SC",
        "Noto Sans SC",
        "Noto Sans CJK JP",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
    )
    available = {f.name for f in fm.fontManager.ttflist}
    for name in preferred:
        if name in available:
            return name
    for name in sorted(available):
        lower = name.lower()
        if any(k in lower for k in ("cjk", "noto sans sc", "wenquanyi", "yahei", "simhei", "source han")):
            return name
    return None


def _setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    font = _resolve_cjk_font()
    if font:
        plt.rcParams["font.sans-serif"] = [font, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _rows_amt_map(payload: dict | None, label_key: str = "prod_tp") -> dict[str, float]:
    if not payload:
        return {}
    rows = payload.get("rows") or []
    result: dict[str, float] = {}
    for row in rows:
        label = str(row.get(label_key, "未知"))
        result[label] = _to_float(row.get("trans_amt", row.get("amt", 0)))
    return result


def chart_1_pie(data_dir: Path, images_dir: Path, plt) -> str | None:
    """饼图：各品类交易金额占比（query_02）。"""
    payload = _load_json(data_dir / "query_02.json")
    if not payload:
        return None
    rows = payload.get("rows") or []
    if not rows:
        return None

    labels = [str(r.get("prod_tp", "未知")) for r in rows]
    values = [_to_float(r.get("trans_amt", r.get("amt", 0))) for r in rows]
    if sum(values) <= 0:
        return None

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    ax.set_title("各品类交易金额占比")
    fig.tight_layout()
    out = images_dir / "chart_1.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out.as_posix()


def chart_2_bar(data_dir: Path, images_dir: Path, plt) -> str | None:
    """柱形图：用户年龄分布交易金额（query_05；query_04 为性别分布）。"""
    payload = _load_json(data_dir / "query_05.json")
    if not payload:
        return None
    rows = payload.get("age") or payload.get("rows") or []
    if not rows:
        return None

    labels = [str(r.get("age_group", r.get("label", "未知"))) for r in rows]
    values = [_to_float(r.get("trans_amt", r.get("amt", 0))) for r in rows]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(labels, values, color="#4C72B0", width=0.6)
    ax.set_title("各年龄段交易金额对比")
    ax.set_ylabel("交易金额（元）")
    plt.xticks(rotation=35, ha="right")
    fig.tight_layout()
    out = images_dir / "chart_2.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out.as_posix()


def chart_3_line(data_dir: Path, images_dir: Path, plt) -> str | None:
    """折线图：各品类当期 vs 基期交易金额（query_02 当期 + query_03 基期）。"""
    current_map = _rows_amt_map(_load_json(data_dir / "query_02.json"))
    base_map = _rows_amt_map(_load_json(data_dir / "query_03.json"))
    if not current_map and not base_map:
        return None

    categories = list(dict.fromkeys([*current_map.keys(), *base_map.keys()]))
    if not categories:
        return None

    current_vals = [current_map.get(c, 0.0) for c in categories]
    base_vals = [base_map.get(c, 0.0) for c in categories]
    if sum(current_vals) <= 0 and sum(base_vals) <= 0:
        return None

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(categories, current_vals, marker="o", linewidth=2, label="当期（query_02）")
    ax.plot(categories, base_vals, marker="s", linewidth=2, linestyle="--", label="基期（query_03）")
    ax.set_title("各品类交易金额两期对比（折线图）")
    ax.set_ylabel("交易金额（元）")
    ax.legend(loc="best")
    plt.xticks(rotation=25, ha="right")
    ax.grid(True, linestyle=":", alpha=0.5)
    fig.tight_layout()
    out = images_dir / "chart_3.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out.as_posix()


CHART_TYPE_RULES = {
    "pie": "占比 / 构成 / 结构（各部分占整体百分比）",
    "line": "时间趋势 / 两期或多期对比趋势（环比、同比、当期 vs 基期）",
    "bar": "各数据项之间横向对比（品类、年龄段、城市、商户等离散维度）",
}

CHART_REGISTRY: dict[str, tuple[str, str, callable]] = {
    "chart_1": ("pie", "饼图", chart_1_pie),   # 占比
    "chart_2": ("bar", "柱形图", chart_2_bar),  # 数据项对比
    "chart_3": ("line", "折线图", chart_3_line),  # 趋势/两期对比
}

# Markdown 嵌入：占位符替换 + 无占位时的回退插入点
CHART_EMBED: dict[str, dict] = {
    "chart_1": {
        "md_line": "![各品类交易金额占比](images/chart_1.png)",
        "placeholders": [
            "【图：各品类交易金额占比】",
            "【图：各品类占比】",
        ],
        "insert_before": "  **分析结论与建议**：家电仍为",
    },
    "chart_2": {
        "md_line": "![用户年龄分布](images/chart_2.png)",
        "placeholders": [
            "【图：用户年龄分布】",
            "【图：年龄分布】",
        ],
        "insert_before": "### 用户城市分布",
    },
    "chart_3": {
        "md_line": "![各品类交易金额环比对比](images/chart_3.png)",
        "placeholders": [
            "【图：各品类交易金额环比对比】",
            "【图：各品类环比对比】",
            "【图：各品类环比】",
        ],
        "insert_after_md": "![各品类交易金额占比](images/chart_1.png)",
    },
}


def _already_embedded(text: str, chart_id: str) -> bool:
    return f"](images/{chart_id}.png)" in text


def embed_charts_in_report(report_path: Path, chart_ids: list[str]) -> tuple[bool, list[str], list[str]]:
    """将已生成图表的 Markdown 引用写入 report.md。"""
    if not report_path.is_file():
        return False, [], [f"report.md 不存在: {report_path.as_posix()}"]

    text = report_path.read_text(encoding="utf-8")
    embedded: list[str] = []
    notes: list[str] = []

    for chart_id in chart_ids:
        if chart_id not in CHART_EMBED:
            continue
        if _already_embedded(text, chart_id):
            embedded.append(chart_id)
            continue

        meta = CHART_EMBED[chart_id]
        md_line = meta["md_line"]
        replaced = False

        for placeholder in meta.get("placeholders", []):
            if placeholder in text:
                text = text.replace(placeholder, md_line, 1)
                replaced = True
                break

        if not replaced:
            insert_after = meta.get("insert_after_md")
            if insert_after and insert_after in text:
                text = text.replace(insert_after, f"{insert_after}\n\n{md_line}", 1)
                replaced = True
            else:
                insert_before = meta.get("insert_before")
                if insert_before and insert_before in text:
                    text = text.replace(insert_before, f"{md_line}\n\n{insert_before}", 1)
                    replaced = True

        if replaced:
            embedded.append(chart_id)
        else:
            notes.append(f"{chart_id}: 未找到占位符，未能写入 report.md")

    if embedded:
        report_path.write_text(text, encoding="utf-8")

    return bool(embedded), embedded, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate charts for yijiu-huanxin report")
    parser.add_argument(
        "--run-dir",
        default=".",
        help="Relative to OUTPUT_DIR cwd; default '.' is sandbox root",
    )
    parser.add_argument(
        "--only",
        choices=("all", "chart_1", "chart_2", "chart_3"),
        default="all",
        help="Which chart(s) to generate",
    )
    parser.add_argument(
        "--no-embed-md",
        action="store_true",
        help="仅生成 PNG，不写入 report.md",
    )
    args = parser.parse_args()

    root = _worktree_root()
    run_dir = (root / args.run_dir).resolve()
    if not str(run_dir).startswith(str(root)):
        print(json.dumps({"ok": False, "error": "run-dir 必须在 OUTPUT_DIR（当前 cwd）下"}, ensure_ascii=False))
        return 1
    if not run_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"目录不存在: {run_dir}"}, ensure_ascii=False))
        return 1

    data_dir = run_dir / "data"
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    try:
        plt = _setup_matplotlib()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"matplotlib 不可用: {exc}"}, ensure_ascii=False))
        return 1

    generated: list[dict[str, str]] = []
    errors: list[str] = []

    names = list(CHART_REGISTRY) if args.only == "all" else [args.only]
    for name in names:
        chart_type, type_label, fn = CHART_REGISTRY[name]
        try:
            path = fn(data_dir, images_dir, plt)
            if path:
                generated.append(
                    {"id": name, "type": chart_type, "type_label": type_label, "path": path}
                )
            else:
                errors.append(f"{name}({type_label}): 缺少 data 或有效数值")
        except Exception as exc:
            errors.append(f"{name}({type_label}): {exc}")

    report_md = run_dir / "report.md"
    embedded_in_md: list[str] = []
    embed_notes: list[str] = []
    if generated and not args.no_embed_md:
        ok, embedded_in_md, embed_notes = embed_charts_in_report(
            report_md, [item["id"] for item in generated]
        )
        if not ok and embed_notes:
            errors.extend(embed_notes)

    result = {
        "ok": bool(generated),
        "run_dir": run_dir.relative_to(root).as_posix(),
        "generated": [item["path"] for item in generated],
        "charts": generated,
        "report_md": report_md.relative_to(root).as_posix() if report_md.is_file() else None,
        "embedded_in_md": embedded_in_md,
        "embed_notes": embed_notes,
        "chart_type_rules": CHART_TYPE_RULES,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if generated else 1


if __name__ == "__main__":
    sys.exit(main())
