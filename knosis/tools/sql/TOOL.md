---
name: sql
version: "0.1"
kind: program
modality: [table, tables]
stage: [explore, extract, refine, decide]
license: "Apache-2.0 (bundled with Knosis; the idea comes from BI-Agent's SQL execution tool)"
---

Loads a set of CSV / parquet tables into an in-memory SQLite database, runs SQL, and writes the result of the last statement that returns rows to `result.csv`.
Table names come from file names: non-alphanumerics become underscores, and a leading digit gets an underscore prefix (e.g. `Share of woman.csv` → `Share_of_woman`).
Column names are kept as is; quote them with double quotes when they contain spaces.

```bash
knosis tool run sql -- --tables data/ --list --out stages/1_explore/sql
knosis tool run sql -- --tables data/ --query 'SELECT COUNT(*) FROM train' --out stages/1_explore/sql
knosis tool run sql -- --tables data/a.csv data/b.csv --file q.sql --out stages/4_decide/sql
```

Exactly one of `--query`, `--file` or `--list` is required. `--tables` takes files or directories (directories expand to their csv / parquet files; files starting with `_` are skipped).
`--list` only outputs table names, source files, row counts and column names. Results are not knowledge, so no κ is produced; `units.jsonl` is empty.
