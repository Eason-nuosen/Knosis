## 目标

使用当前知识层完成下游任务；只采用仍有效的知识，不使用 stale 或 retracted 单元。
知识正确不等于对这些题有用：先用 `knosis knowledge select` 挑出相关知识、`knosis knowledge skills` 看有没有适用的解法，
再决定用哪些；用到的 skill 在 `used_units` 里写成 `skill:<名字>`。

## 输入

`tasks/tasks.jsonl`、`kb/knowledge/units.jsonl`、`kb/knowledge/ontology/`、`kb/skills/`、`data/`。
Python：`$python`。

## 交付物

`stages/4_decide/$output`。
图问答 JSONL 每行含 id 与 answer，答案形状见 BRIEF；
表格 CSV 含 row_id 与 prediction，分类可附各类概率。
`stages/4_decide/used_units.jsonl`（建议）：每行 `{"id": 题目或 row_id, "used_units": [知识 id, ...]}`，
用于评估知识是否真正参与了决策。

## 验收标准

每道题或测试行恰有一个输出，没有未知或重复 id；不能寻找测试答案。
完成后运行 `knosis ws check .`。
$control