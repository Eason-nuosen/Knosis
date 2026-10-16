---
name: joins
version: "0.1"
kind: program
modality: [tables]
stage: [explore, extract]
license: "Apache-2.0（Knosis 自带；对应 BI-Agent 的 discover_join_relationships，但实时计算、不读预置答案）"
---

多表 join 发现：找出「外键列的取值几乎都出现在另一张表的唯一列里」的列对（包含依赖），
按包含率与列名相似度排序，输出 `joins.csv`，每个候选一条 `finding`（inferred）。
`--ontology DIR` 另写一份本体 core 层草稿（`<name>.semantic_model.yaml`：表、列、候选主键、候选 join），
provenance 记为 `method: tool`，可直接放进 `knowledge/ontology/` 再由 agent 修订。

```bash
knosis tool run joins -- --tables data/ --out stages/1_explore/joins
knosis tool run joins -- --tables data/ --out stages/2_extract/joins --min-containment 0.95 --ontology stages/2_extract/joins/ontology
```

默认还要求两列列名相似度（difflib）≥ `--min-name-similarity 0.5`，设为 0 即只看取值。
参考：在 BI-Bench 前 25 个用例上与 Power BI 模型自带的关系对照，默认参数精确率 0.35、召回 0.63
（只看包含率时为 0.10 / 0.69）；模型自带关系并不完整，精确率是下界。

只比较整数与字符串列（统一转成字符串比较，`1.0` 与 `1` 视为相同），不比较布尔与小数列；
外键侧至少 `--min-distinct` 个不同值，避免把常数列当外键。包含率高不等于语义上可 join，需要再验证。
