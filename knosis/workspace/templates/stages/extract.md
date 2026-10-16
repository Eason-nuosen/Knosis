## 目标

提取服务下游任务且能复用的事实、规则、模式、方程与 schema 约束。
写清成立条件与例外，不要把具体题目的答案存成知识。

## 输入

`BRIEF.md`、`data/`、`stages/1_explore/notes.md`、已有 finding 和 `TOOLS.md`。
Python：`$python`。

## 交付物

更新 `knowledge/units.jsonl`，可以追加、修改或撤回已有单元。
结构性知识（schema、join、概念与映射）可写成 `knowledge/ontology/` 下的本体，κ 用 `about` 引用。
分析与验证代码放在 `stages/2_extract/`。

## 验收标准

知识层（κ 或本体）非空且结构检查通过；每条知识记录 condition。
规则与方程在数据上验证，meta 报告支持样本数与反例数；
已验证的标为 verified，派生知识记录 derived_from。
完成后运行 `knosis ws check .`，通过后保存 K_0 快照。
