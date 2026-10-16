## 目标

第 $round 轮改进知识层：合并重复、概括条件规则、重新验证、修复冲突，
撤回不成立的知识，并将受影响的派生知识标为 stale。

## 输入

当前 `knowledge/units.jsonl` 与 `knowledge/ontology/`、`data/`、前几轮 changelog、`TOOLS.md`。
Python：`$python`。

## 交付物

更新 `knowledge/units.jsonl`；
`stages/3_refine/round_$round/changelog.md` 记录变更、理由和数据验证结果。
代码与工具结果放在当前轮目录。

## 验收标准

I1 来源与派生引用完整，I5 撤回传播通过；本体的跨文件引用与 κ 的 `about` 引用可解析。
合并单元的 derived_from 指向原单元，不得丢掉来源、成立条件与例外。
完成后运行 `knosis ws check .`，通过后保存 K_$round；
轮次自行决定，结束时运行 `knosis ws goto . decide`。
