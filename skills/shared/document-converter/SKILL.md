---
name: document-converter
description: 在 Markdown、DOCX、PDF 之间双向转换；MD→DOCX/PDF 时用 Pandoc + 样式模板优化表格与图片。用户要求导出 Word/PDF、从 Word/PDF 抽 Markdown、或批量转文档时使用。
---

# Document Converter Skill

将文档在 **Markdown ↔ DOCX ↔ PDF** 间转换。优先走本 Skill 自带脚本（自动选工具 + 报告向 CSS），产物默认落在 **OUTPUT_DIR**。

## 工作区与路径

- `bash` 的 cwd = `OUTPUT_DIR`（默认 `.output/`）
- 源文件 / 输出路径都写**相对 OUTPUT_DIR** 的名字，例如 `report.md`、`exports/report.docx`
- **不要**再写 `.output/` 前缀
- 脚本相对路径：`../skills/shared/document-converter/scripts/convert.py`

```
OUTPUT_DIR/
├── report.md              ← 常见输入
├── images/                ← MD 内相对图片
└── exports/               ← 建议输出目录
    ├── report.docx
    └── report.pdf
```

## 何时使用

- 用户要把 `.md` 转成 `.docx` / `.pdf`（含表格、图片要好看）
- 从 `.docx` / `.pdf` 提取为 Markdown
- PDF 直接转 DOCX（保留版式）
- 批量转换某目录下同类型文件

**不要用于：** 只改 MD 正文内容（用 `edit_file`）；以旧换新月报写作流程（先 `yijiu-huanxin-reporter`）。

## 依赖（按需）

| 工具 | 用途 | 安装 |
|------|------|------|
| `pandoc` | MD→DOCX / MD→PDF 主路径 | `apt install pandoc`（本机通常已有） |
| `weasyprint` | 美观 PDF（表格斑马纹、图片缩放、中文） | `pip install weasyprint` |
| `markitdown` | DOCX/PDF→MD | `pip install markitdown` |
| `pdf2docx` | PDF→DOCX 直转 | `pip install pdf2docx` |
| `pymupdf4llm` | PDF→MD 备选 | `pip install pymupdf4llm`（可选） |

先探测：

```bash
python ../skills/shared/document-converter/scripts/convert.py --check
```

## 标准流程

### 1. 加载本 Skill

```
load_skill("document-converter")
```

### 2. 确认输入在 OUTPUT_DIR

- 已有 `report.md` 或用户指定文件
- 图片用相对路径（如 `images/chart_1.png`），与 MD 同沙箱

### 3. 执行转换（在 OUTPUT_DIR 下 bash）

**Markdown → DOCX + PDF（一次出两种）：**

```bash
python ../skills/shared/document-converter/scripts/convert.py \
  --input report.md \
  --to docx,pdf \
  --output-dir exports
```

**仅 DOCX：**

```bash
python ../skills/shared/document-converter/scripts/convert.py -i report.md -t docx -o exports/report.docx
```

**仅精美 PDF（WeasyPrint + 内置 report.css）：**

```bash
python ../skills/shared/document-converter/scripts/convert.py -i report.md -t pdf -o exports/report.pdf
```

**DOCX / PDF → Markdown：**

```bash
python ../skills/shared/document-converter/scripts/convert.py -i source.docx -t md -o exports/source.md
python ../skills/shared/document-converter/scripts/convert.py -i source.pdf -t md -o exports/source.md
```

**PDF → DOCX：**

```bash
python ../skills/shared/document-converter/scripts/convert.py -i source.pdf -t docx -o exports/source.docx
```

**批量（目录内同方向）：**

```bash
python ../skills/shared/document-converter/scripts/convert.py --input-dir . --to pdf --output-dir exports --glob "*.md"
```

### 4. 检查结果

- 脚本 stdout 打印 JSON：`ok`、`outputs`、`engine`、`warnings`
- 用 `bash` 确认文件存在：`ls -la exports/`
- PDF/DOCX 中表格应有表头底色与边框；图片不应溢出页宽

## 排版约定（MD→PDF/DOCX）

为让表格与图片更美观，源 MD 建议：

1. 表格用标准 pipe table，表头清晰
2. 图片：`![说明](images/xxx.png)`，宽度交给 CSS（`max-width:100%`）
3. 标题层级连续（`#` → `##` → `###`）
4. 中文正文无需额外配置；PDF 模板已带 CJK 字体回退

自定义 CSS（可选）：

```bash
python ../skills/shared/document-converter/scripts/convert.py -i report.md -t pdf \
  --css ../skills/shared/document-converter/templates/report.css
```

## 工具优先级（脚本内置）

| 方向 | 优先 | 回退 |
|------|------|------|
| MD → DOCX | pandoc | — |
| MD → PDF | pandoc + weasyprint + CSS | pandoc 默认引擎（若可用） |
| DOCX → MD | markitdown | pandoc |
| PDF → MD | markitdown | pymupdf4llm → pandoc |
| PDF → DOCX | pdf2docx | — |

## Agent 自检

- [ ] 已 `load_skill("document-converter")`
- [ ] 路径相对 OUTPUT_DIR，无多余 `.output/`
- [ ] `--check` 或转换 JSON 中无缺依赖错误
- [ ] 目标文件已生成且体积 > 0
- [ ] 若含图：导出后抽查图片未丢；若含表：非纯纯文本糊成一段

## 故障速查

| 现象 | 处理 |
|------|------|
| `pandoc: not found` | 安装 pandoc |
| weasyprint / 中文方框 | `apt install fonts-noto-cjk` 或把字体放入系统 |
| 图片丢失 | 确认 MD 相对路径相对 MD 文件；脚本会设 `--resource-path` |
| 权限询问 | 破坏性 bash 会 HITL；转换脚本本身只写 OUTPUT_DIR |
