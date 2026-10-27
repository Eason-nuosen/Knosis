## 目标

第 $round 轮改进知识层，使它更能支持下游任务。数据可能含噪声，如何判断与处理由你决定。
可以合并重复（被并的改为 merged + merged_into）、概括条件规则、重新验证、处理矛盾，撤回不成立的知识，并将受影响的派生知识标为 stale。
反馈结果本身也是知识的来源：从中得到的结论照常写成 κ，反馈对某条知识的支持或反驳记为证据（method=feedback）。
继承来的知识与本体同样可以修正；修正时保留证据链。
回看反馈后，把「怎样用知识解这类题」总结成 skill（新建或修改 `kb/skills/`）。

## 输入

当前 `kb/`（knowledge/units.jsonl、knowledge/ontology/、skills/）与 `evidence/`（ledger.jsonl、feedback/）、`data/`、前几轮 changelog、`TOOLS.md`。
Python：`$python`。

$feedback

## 交付物

更新 `kb/knowledge/units.jsonl`（需要时也更新本体与 skill）；
`stages/3_refine/round_$round/changelog.md` 记录变更、理由和验证结果。
有 dev 题时，用本轮的知识回答并写到 `stages/3_refine/round_$round/dev_$output`，
同目录可附 `dev_<同名>_used_units.jsonl`（每行 `{"id": 题目, "used_units": [知识 id 或 skill:<名字>]}`）：
提交反馈时 Knosis 据此按题型统计每条知识与 skill 的效用（scope=usage 的候选与证据）；
驱动模式下运行器在本轮结束时会自动提交它拿一次反馈，结果出现在下一轮的提示里。
代码与工具结果放在当前轮目录。

## 验收标准

I1 来源与派生引用完整，I5 撤回传播通过；状态与证据一致；本体的跨文件引用与 κ 的 `about` 引用可解析；
`feedback:` 来源指向存在的反馈记录。合并单元的 derived_from 指向原单元，不得丢掉来源、成立条件与例外。
完成后运行 `knosis ws check .`，通过后保存 K_$round；
轮次自行决定，结束时运行 `knosis ws goto . decide`。
$control