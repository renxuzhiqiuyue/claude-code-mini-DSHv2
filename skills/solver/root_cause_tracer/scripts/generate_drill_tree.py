"""Generate root-cause decision tree PNG from data/root_01.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _worktree_root() -> Path:
    """Agent bash cwd: OUTPUT_DIR（默认 .output）。"""
    return Path.cwd().resolve()


def _load_root_payload(run_dir: Path) -> dict:
    path = run_dir / "data" / "root_01.json"
    if not path.is_file():
        raise FileNotFoundError(f"缺少根因数据: {path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_delta(value: float) -> str:
    sign = "+" if value >= 0 else ""
    if abs(value) >= 10000:
        return f"{sign}{value / 10000:.2f}万"
    return f"{sign}{value:.0f}"


def render_graphviz(result: dict, out_path: Path) -> str:
    try:
        from graphviz import Digraph
    except ImportError as exc:
        raise RuntimeError("请安装 graphviz: pip install graphviz，并 apt install graphviz") from exc

    metric = result.get("metric", "metric")
    overall = result.get("overall", {})
    delta = overall.get("delta", 0)
    tree = result.get("tree") or {}
    nodes = {n["id"]: n for n in tree.get("nodes", [])}
    edges = tree.get("edges", [])

    if not nodes:
        raise ValueError("root_01.json 缺少 tree.nodes，请先运行 build_root_cause_tree")

    graph = Digraph("root_cause_tree", format="png")
    graph.attr(rankdir="TB", splines="polyline", nodesep="0.5", ranksep="0.55")
    graph.attr("node", fontname="Noto Sans CJK SC,Microsoft YaHei,SimHei,sans-serif")
    graph.attr("edge", fontname="Noto Sans CJK SC,Microsoft YaHei,SimHei,sans-serif")

    ranks: dict[int, list[str]] = {}
    for node_id, node in nodes.items():
        rank = node.get("rank", 0)
        ranks.setdefault(rank, []).append(node_id)

    for node_id, node in nodes.items():
        label = node.get("label", node_id)
        kind = node.get("kind", "default")
        if kind == "root":
            graph.node(node_id, label, shape="ellipse", style="filled", fillcolor="#E8F4FD")
        elif kind == "dimension":
            graph.node(node_id, label, shape="box", style="rounded,filled", fillcolor="#FFF3CD")
        elif kind == "merge":
            graph.node(
                node_id,
                label,
                shape="diamond",
                style="filled",
                fillcolor="#D1ECF1",
                fontsize="10",
            )
        elif kind == "other":
            graph.node(node_id, label, shape="box", style="rounded,filled", fillcolor="#E9ECEF")
        else:
            graph.node(node_id, label, shape="box", style="rounded")

    for rank, ids in sorted(ranks.items()):
        if len(ids) > 1:
            with graph.subgraph(name=f"rank_{rank}") as sub:
                sub.attr(rank="same")
                for node_id in ids:
                    sub.node(node_id)

    for edge in edges:
        attrs = {}
        if edge.get("style") == "dashed":
            attrs["style"] = "dashed"
        if edge.get("label"):
            attrs["label"] = edge["label"]
        graph.edge(edge["from"], edge["to"], **attrs)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = graph.render(out_path.with_suffix(""), cleanup=True)
    return rendered


def embed_in_report(report_path: Path, chart_rel: str = "images/chart_root.png") -> bool:
    if not report_path.is_file():
        return False
    text = report_path.read_text(encoding="utf-8")
    md_line = f"![根因下钻决策树]({chart_rel})"
    if md_line in text or f"]({chart_rel})" in text:
        return False
    placeholders = [
        "【图：根因下钻决策树】",
        "【图：根因决策树】",
    ]
    for ph in placeholders:
        if ph in text:
            report_path.write_text(text.replace(ph, md_line, 1), encoding="utf-8")
            return True
    marker = "### 主因维度"
    if marker in text:
        report_path.write_text(text.replace(marker, f"{md_line}\n\n{marker}", 1), encoding="utf-8")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate root cause decision tree PNG")
    parser.add_argument(
        "--run-dir",
        default=".",
        help="Relative to OUTPUT_DIR cwd; default '.' is sandbox root",
    )
    parser.add_argument("--no-embed-md", action="store_true")
    args = parser.parse_args()

    root = _worktree_root()
    run_dir = (root / args.run_dir).resolve()
    if not str(run_dir).startswith(str(root)):
        print(json.dumps({"ok": False, "error": "run-dir 必须在 OUTPUT_DIR（当前 cwd）下"}, ensure_ascii=False))
        return 1

    try:
        payload = _load_root_payload(run_dir)
        result = payload.get("result", payload)
        if not result.get("success"):
            print(json.dumps({"ok": False, "error": "root_01 根因分析未成功"}, ensure_ascii=False))
            return 1

        out_path = run_dir / "images" / "chart_root.png"
        png_path = render_graphviz(result, out_path)

        embedded = False
        if not args.no_embed_md:
            embedded = embed_in_report(run_dir / "report.md")

        print(
            json.dumps(
                {
                    "ok": True,
                    "path": png_path,
                    "embedded_in_md": embedded,
                    "report_md": (run_dir / "report.md").relative_to(root).as_posix(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
