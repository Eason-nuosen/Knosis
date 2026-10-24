# 内化 1/3：去重

知识层根目录：`$base`（$n_units 条活跃 κ，$n_inactive 条已失效）。目标：把说同一件事的单元合并成一条，让以后检索到的知识不重复。

## 候选

Knosis 按内容相似度与共同锚定对象找出的疑似重复（只是提示，未必都是重复）：

$candidates

也可以用 `knosis knowledge select --ws $base --text <关键词>` 自己再找。

## 做法

1. 逐对判断是不是同一件事：同一对象、同一断言、条件兼容。只是相关、条件不同、粒度不同（一条讲具体对象、一条讲整体规律）的不算重复。
2. 是重复：保留更准确、条件更完整、证据更多的一条作为主单元；需要时改写它的 `content` / `condition`，把两条的信息合起来，
   不丢成立条件与例外；`provenance` 合并两条的来源（用 ` ; ` 连接）。
3. 另一条改为 `"status": "merged"`，加 `"merged_into": "<主单元 id>"`，其余字段原样保留（它成为别名，引用它的派生单元、skill、
   大纲都会按别名解析到主单元）。被并单元的证据不用搬。
4. 不删除任何单元；只改 `kb/knowledge/units.jsonl`。需要补证据时用
   `knosis knowledge evidence add --ws $base --unit <主单元> --verdict support --method derivation --source merge:<被并单元> --note "<依据>"`。

## 验收

`knosis knowledge check --ws $base` 不新增问题$check_note；没有单元被删除。
最后用两三句话说明合并了哪些，哪些候选不是重复、为什么。
