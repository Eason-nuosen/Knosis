# 内化：压缩

知识层根目录：`$base`（$n_units 条活跃 κ，$n_inactive 条已失效）。目标：$goal

## 范围

$scope

可以用 `knosis knowledge select --ws $base --text <关键词>` 自己再找，`knosis knowledge trace <id> --ws $base` 看一条知识的来历。

## 做法

压缩只减少条数，不丢信息：被压缩掉的单元都要能沿别名找到概括它的那条。

1. 找出可以合起来说的一组单元：同一对象的多条零散断言、同一规律在多个对象上的实例、相近的方法步骤、措辞不同的同一件事。
   条件不同、相互矛盾、粒度跨度大到合起来会丢信息的不要合。
2. 每组保留一条作为主单元（也可以新建一条概括单元）：改写它的 `content` / `condition`，把组内的成立条件、例外、关键数字都写进去；
   `provenance` 合并组内各条的来源（用 ` ; ` 连接）；新建的概括单元 `status` 取组内最弱的状态（有 verified 也只能写 inferred，
   除非给它补证据：`knosis knowledge evidence add --ws $base --unit <主单元> --verdict support --method derivation --source merge:<被并单元> --note "<依据>"`）。
3. 组内其余单元改为 `"status": "merged"`，加 `"merged_into": "<主单元 id>"`，其余字段原样保留（它们成为别名，引用它们的派生单元、skill、
   大纲都会按别名解析到主单元）。
4. 价值很低、已被别的单元完整覆盖的单元，同样并入覆盖它的那条（merged），不要直接撤回。
5. 不删除任何单元；改 `kb/knowledge/units.jsonl`（和必要的证据）。大纲 `kb/outline.yaml`、知识图谱 `kb/graph.json`、流程图 `kb/flows/` 里
   对被并单元的引用改指主单元（同一处引用重复了就去掉一个），不做其他改动。$topic_rule

## 验收

`knosis knowledge check --ws $base` 不新增问题$check_note；没有单元被删除；活跃单元数减少；这一步变为失效的单元都有 `merged_into`
（或 `superseded_by`）指向活跃单元。确实没有可压缩的就什么都不改。
最后用两三句话说明压缩了哪几组、各组为什么能合，哪些看起来相近但没有合、为什么。
