---
name: profile
version: "0.1"
kind: program
modality: [table, tables]
stage: [explore, extract]
license: "Apache-2.0（Knosis 自带）"
---

表格画像：每列的类型、缺失率、不同值个数、是否唯一、取值范围与样例，输出 `profile.csv`。
同时产出 κ：每张表一条 `schema`（行数、候选主键，observed），
以及可疑项 `finding`（inferred）：常数列、高缺失列、疑似宽表（多列列名像年份 / 月份 / 日期，
可能需要 unpivot，对应 BI-Agent 的 transform 工具）。

```bash
knosis tool run profile -- --tables data/ --out stages/1_explore/profile
knosis tool run profile -- --tables data/train.parquet --out stages/1_explore/profile --max-missing 0.3
```

来源写成传入的路径加 `#col/<列名>`，在工作区内请传 `data/...` 相对路径，以便 `ws check` 定位。
