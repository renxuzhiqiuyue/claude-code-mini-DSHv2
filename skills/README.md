# Skills 目录隔离

```
skills/
├── planner/   # 仅 Planner 可见 / 可 load_skill
├── solver/    # 仅 Solver 可见 / 可 load_skill
└── shared/    # 两边共用
```

| 角色 | 扫描目录 |
|------|----------|
| Planner | `planner/` + `shared/` |
| Solver | `solver/` + `shared/` |

脚本路径（在 OUTPUT_DIR 下执行）示例：

- `python ../skills/solver/local_chart/scripts/generate_charts.py --run-dir .`
- `python ../skills/shared/document-converter/scripts/convert.py -i report.md -t docx,pdf -o exports`
