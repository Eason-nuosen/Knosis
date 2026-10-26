---
name: sheet
version: "0.1"
kind: program
modality: [spreadsheet]
stage: [explore, extract, refine, decide]
license: "Apache-2.0（Knosis 自带）"
---

电子表格（xlsx / xlsm）的结构查看与公式重算，两个子命令：

- `inspect`：每个 sheet 的已用范围、合并单元格、数据验证、条件格式数、公式单元格数，以及指定区域内每格的值、公式与数值格式。
  公式单元格同时给出缓存值（openpyxl `data_only=True` 读到的值；用 openpyxl 写入的公式没有缓存值，读出来是 None）。
  产出 κ：每个 sheet 一条 `schema`（已用范围、合并单元格、公式数，observed）。
- `recalc`：用 LibreOffice 打开文件、重算公式并另存（与评测时的处理相同），再按 `--range` 读出重算后的值。
  用来确认自己写的公式在评测时会算出什么。

```bash
knosis tool run sheet -- inspect data/13-1/1_input.xlsx --out stages/1_explore/sheet_13-1
knosis tool run sheet -- inspect data/13-1/1_input.xlsx --range "LISTS!A1:E20" --out stages/1_explore/sheet_13-1
knosis tool run sheet -- recalc stages/4_decide/outputs/13-1/1_output.xlsx --range "LISTS!A3:D32" --out stages/4_decide/recalc
```

`--range` 写法同 SpreadsheetBench 的 `answer_position`：`A1:D10`、`'Sheet 1'!A1:D10`，多段用逗号分隔；
不写 sheet 时取第一个 sheet。`inspect` 不给 `--range` 时每个 sheet 只列左上角最多 30 行 × 15 列。
需要 openpyxl；`recalc` 需要 LibreOffice（`KNOSIS_SOFFICE` 可指定 soffice 路径）。
