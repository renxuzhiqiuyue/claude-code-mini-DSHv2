#!/usr/bin/env python3
"""document-converter：Markdown / DOCX / PDF 互转（适配 OUTPUT_DIR 工作区）。

用法（在 OUTPUT_DIR 下）:
  python ../skills/shared/document-converter/scripts/convert.py --check
  python ../skills/shared/document-converter/scripts/convert.py -i report.md -t docx,pdf -o exports
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSS = SKILL_ROOT / "templates" / "report.css"


def _which(name: str) -> str | None:
    return shutil.which(name)


def _can_import(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def detect_tools() -> dict:
    return {
        "pandoc": bool(_which("pandoc")),
        "weasyprint_cli": bool(_which("weasyprint")),
        "weasyprint_py": _can_import("weasyprint"),
        "markitdown": _can_import("markitdown"),
        "pdf2docx": _can_import("pdf2docx"),
        "pymupdf4llm": _can_import("pymupdf4llm"),
    }


def _run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return 124, f"超时（{timeout}s）: {' '.join(cmd)}"
    except Exception as e:
        return 1, str(e)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _resolve_under_cwd(p: str | Path) -> Path:
    path = Path(p).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return path


def md_to_docx(src: Path, dst: Path) -> dict:
    if not _which("pandoc"):
        return {"ok": False, "error": "需要 pandoc"}
    _ensure_parent(dst)
    resource = str(src.parent)
    code, out = _run(
        [
            "pandoc",
            str(src),
            "-o",
            str(dst),
            f"--resource-path={resource}",
            "-f",
            "markdown",
            "-t",
            "docx",
        ]
    )
    return {
        "ok": code == 0 and dst.exists(),
        "engine": "pandoc",
        "output": str(dst),
        "log": out[:2000],
    }


def md_to_pdf(src: Path, dst: Path, css: Path) -> dict:
    if not _which("pandoc"):
        return {"ok": False, "error": "需要 pandoc"}
    _ensure_parent(dst)
    resource = str(src.parent)
    css_path = css if css.exists() else DEFAULT_CSS
    warnings: list[str] = []

    # 优先：pandoc → HTML → weasyprint（表格/图/中文更稳）
    if _can_import("weasyprint") or _which("weasyprint"):
        html_tmp = dst.with_suffix(".tmp.html")
        code, out = _run(
            [
                "pandoc",
                str(src),
                "-o",
                str(html_tmp),
                "-s",
                f"--resource-path={resource}",
                f"--css={css_path}",
                "-f",
                "markdown",
                "-t",
                "html5",
            ]
        )
        if code != 0:
            return {"ok": False, "engine": "pandoc-html", "error": out[:2000]}
        try:
            if _can_import("weasyprint"):
                from weasyprint import HTML

                HTML(filename=str(html_tmp), base_url=str(src.parent)).write_pdf(str(dst))
                engine = "pandoc+weasyprint(py)"
            else:
                code2, out2 = _run(
                    ["weasyprint", str(html_tmp), str(dst)],
                    timeout=300,
                )
                if code2 != 0:
                    return {"ok": False, "engine": "weasyprint-cli", "error": out2[:2000]}
                engine = "pandoc+weasyprint(cli)"
        except Exception as e:
            return {"ok": False, "engine": "weasyprint", "error": str(e)}
        finally:
            if html_tmp.exists():
                html_tmp.unlink(missing_ok=True)
        return {
            "ok": dst.exists() and dst.stat().st_size > 0,
            "engine": engine,
            "output": str(dst),
            "css": str(css_path),
            "warnings": warnings,
        }

    # 回退：pandoc 自带 pdf 引擎
    code, out = _run(
        [
            "pandoc",
            str(src),
            "-o",
            str(dst),
            f"--resource-path={resource}",
        ]
    )
    if code != 0:
        warnings.append("未安装 weasyprint，且 pandoc 直接出 PDF 失败；请 pip install weasyprint")
    return {
        "ok": code == 0 and dst.exists(),
        "engine": "pandoc",
        "output": str(dst),
        "log": out[:2000],
        "warnings": warnings,
    }


def to_markdown(src: Path, dst: Path) -> dict:
    _ensure_parent(dst)
    suffix = src.suffix.lower()

    if _can_import("markitdown"):
        try:
            from markitdown import MarkItDown

            md = MarkItDown()
            result = md.convert(str(src))
            text = getattr(result, "text_content", None) or str(result)
            dst.write_text(text, encoding="utf-8")
            return {
                "ok": True,
                "engine": "markitdown",
                "output": str(dst),
            }
        except Exception as e:
            markitdown_err = str(e)
    else:
        markitdown_err = "markitdown 未安装"

    if suffix == ".pdf" and _can_import("pymupdf4llm"):
        try:
            import pymupdf4llm

            text = pymupdf4llm.to_markdown(str(src))
            dst.write_text(text, encoding="utf-8")
            return {
                "ok": True,
                "engine": "pymupdf4llm",
                "output": str(dst),
                "warnings": [f"markitdown 不可用: {markitdown_err}"],
            }
        except Exception as e:
            pymu_err = str(e)
    else:
        pymu_err = "跳过"

    if _which("pandoc"):
        code, out = _run(["pandoc", str(src), "-o", str(dst), "-t", "markdown"])
        return {
            "ok": code == 0 and dst.exists(),
            "engine": "pandoc",
            "output": str(dst),
            "log": out[:2000],
            "warnings": [f"markitdown: {markitdown_err}", f"pymupdf4llm: {pymu_err}"],
        }

    return {
        "ok": False,
        "error": f"无法转换：markitdown={markitdown_err}; pymupdf4llm={pymu_err}; 无 pandoc",
    }


def pdf_to_docx(src: Path, dst: Path) -> dict:
    if not _can_import("pdf2docx"):
        return {"ok": False, "error": "需要 pdf2docx：pip install pdf2docx"}
    _ensure_parent(dst)
    try:
        from pdf2docx import Converter

        cv = Converter(str(src))
        cv.convert(str(dst))
        cv.close()
        return {"ok": dst.exists(), "engine": "pdf2docx", "output": str(dst)}
    except Exception as e:
        return {"ok": False, "engine": "pdf2docx", "error": str(e)}


def convert_one(
    src: Path,
    targets: list[str],
    output: Path | None,
    output_dir: Path | None,
    css: Path,
) -> list[dict]:
    results = []
    stem = src.stem
    for t in targets:
        t = t.strip().lower().lstrip(".")
        if t in ("md", "markdown"):
            ext, kind = ".md", "md"
        elif t in ("docx", "doc"):
            ext, kind = ".docx", "docx"
        elif t == "pdf":
            ext, kind = ".pdf", "pdf"
        else:
            results.append({"ok": False, "error": f"不支持目标格式: {t}"})
            continue

        if output and len(targets) == 1:
            dst = output
        elif output_dir:
            dst = output_dir / f"{stem}{ext}"
        elif output and output.suffix:
            dst = output.with_suffix(ext) if len(targets) > 1 else output
        else:
            dst = src.with_suffix(ext)

        dst = _resolve_under_cwd(dst)
        src_s = src.suffix.lower()

        if kind == "docx" and src_s in (".md", ".markdown"):
            results.append(md_to_docx(src, dst))
        elif kind == "pdf" and src_s in (".md", ".markdown"):
            results.append(md_to_pdf(src, dst, css))
        elif kind == "md" and src_s in (".docx", ".doc", ".pdf", ".pptx", ".xlsx", ".html"):
            results.append(to_markdown(src, dst))
        elif kind == "docx" and src_s == ".pdf":
            results.append(pdf_to_docx(src, dst))
        else:
            results.append(
                {
                    "ok": False,
                    "error": f"不支持方向: {src_s} → {ext}",
                    "hint": "支持 md→docx/pdf、docx/pdf→md、pdf→docx",
                }
            )
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="document-converter for claude-code-mini")
    p.add_argument("--check", action="store_true", help="探测可用工具")
    p.add_argument("-i", "--input", help="输入文件（相对 cwd / OUTPUT_DIR）")
    p.add_argument("--input-dir", help="批量：输入目录")
    p.add_argument("--glob", default="*.md", help="批量匹配，默认 *.md")
    p.add_argument(
        "-t",
        "--to",
        default="docx,pdf",
        help="目标格式，逗号分隔：docx,pdf,md",
    )
    p.add_argument("-o", "--output", help="单文件输出路径")
    p.add_argument("--output-dir", help="输出目录（批量或多目标时）")
    p.add_argument(
        "--css",
        default=str(DEFAULT_CSS),
        help="MD→PDF 用 CSS",
    )
    args = p.parse_args(argv)

    tools = detect_tools()
    if args.check:
        print(json.dumps({"ok": True, "tools": tools}, ensure_ascii=False, indent=2))
        return 0

    targets = [x for x in args.to.split(",") if x.strip()]
    css = _resolve_under_cwd(args.css) if not Path(args.css).is_absolute() else Path(args.css)
    if not css.exists():
        css = DEFAULT_CSS

    out_path = _resolve_under_cwd(args.output) if args.output else None
    out_dir = _resolve_under_cwd(args.output_dir) if args.output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[dict] = []
    sources: list[Path] = []

    if args.input_dir:
        base = _resolve_under_cwd(args.input_dir)
        sources = sorted(base.glob(args.glob))
        if not sources:
            print(
                json.dumps(
                    {"ok": False, "error": f"未匹配到文件: {base}/{args.glob}"},
                    ensure_ascii=False,
                )
            )
            return 1
    elif args.input:
        sources = [_resolve_under_cwd(args.input)]
    else:
        print(json.dumps({"ok": False, "error": "请指定 --input 或 --input-dir 或 --check"}, ensure_ascii=False))
        return 1

    for src in sources:
        if not src.exists():
            all_results.append({"ok": False, "input": str(src), "error": "文件不存在"})
            continue
        for item in convert_one(src, targets, out_path, out_dir, css):
            item["input"] = str(src)
            all_results.append(item)

    ok = all(r.get("ok") for r in all_results) if all_results else False
    payload = {
        "ok": ok,
        "tools": tools,
        "results": all_results,
        "outputs": [r.get("output") for r in all_results if r.get("ok") and r.get("output")],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
