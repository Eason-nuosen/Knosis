---
name: profile
version: "0.1"
kind: program
modality: [table, tables]
stage: [explore, extract]
license: "Apache-2.0 (bundled with Knosis)"
---

Table profiling: for each column, the dtype, missing rate, number of distinct values, uniqueness, value range and examples, written to `profile.csv`.
It also produces κ: one `schema` per table (row count, candidate primary keys; observed),
and suspicious-item `finding`s (inferred): constant columns, columns with high missing rates (> `--max-missing`, default 0.5), and likely wide tables (at least `--min-period-columns`, default 4,
column names that look like years / quarters / months / dates, which may need an unpivot; the counterpart of BI-Agent's transform tool).

```bash
knosis tool run profile -- --tables data/ --out stages/1_explore/profile
knosis tool run profile -- --tables data/train.parquet --out stages/1_explore/profile --max-missing 0.3
```

`--tables` takes files or directories (directories expand to their csv / parquet files; files starting with `_` are skipped).
Sources are written as the given path plus `#col/<column>`; inside a workspace, pass relative `data/...` paths so that `ws check` can locate them.
