---
name: sql
version: "0.1"
kind: program
modality: [table, tables]
stage: [explore, extract, refine, decide]
license: "Apache-2.0（Knosis 自带；思路来自 BI-Agent 的 SQL 执行工具）"
---

把一组 CSV / parquet 表载入内存 SQLite，执行 SQL，最后一条语句的结果写入 `result.csv`。
表名由文件名得到：非字母数字转为下划线，数字开头加下划线（如 `Share of woman.csv` → `Share_of_woman`）。
列名保持原样，含空格时用双引号引用。

```bash
knosis tool run sql -- --tables data/ --list --out stages/1_explore/sql
knosis tool run sql -- --tables data/ --query 'SELECT COUNT(*) FROM train' --out stages/1_explore/sql
knosis tool run sql -- --tables data/a.csv data/b.csv --file q.sql --out stages/4_decide/sql
```

`--list` 只输出表名、来源文件与列名。结果不是知识，不产出 κ；`units.jsonl` 为空。
