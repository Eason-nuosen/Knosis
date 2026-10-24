# 内化 2/3：矛盾处理

知识层根目录：`$base`（$n_units 条活跃 κ）。目标：同一对象上互相矛盾的断言要么化解，要么明确标出，不能让知识库自相矛盾。

## 候选

锚定在同一对象上的相关单元，以及有争议的单元（只是提示）：

$candidates

## 做法

逐个判断是否真的互斥（同一对象、同一条件下不可能同时成立）。真矛盾有三条出路：

1. **收窄条件**：两条在不同条件下都成立（不同子集、时间段、版本、参数范围）。改写各自的 `condition` 写清范围，必要时重新验证。
2. **用新证据裁决**：$verify 记下证据后，被推翻的一方改为 `retracted`（它的后代按撤回传播改为 stale / retracted）。
3. **环境变了**：旧结论曾经成立，但数据、工具或环境版本变了。旧单元改为 `stale` 并加 `"superseded_by": "<新单元 id>"`。

暂时无法裁决的：双方互相加 `"conflicts_with": ["<对方 id>"]`，至少一方改为 `contested`（contested 默认不被选取，等以后有证据再定）。
不删除任何单元；只改 `kb/knowledge/units.jsonl`，证据用 `knosis knowledge evidence add --ws $base ...` 记。

## 验收

`knosis knowledge check --ws $base` 不新增问题$check_note；`conflicts_with` 的每一对，如果都还活跃，至少一方是 contested。
最后用两三句话说明处理了哪些矛盾、各走的哪条出路，哪些候选并不矛盾。
