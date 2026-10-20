## 目标

读懂数据的结构、分布与质量。数据可能含噪声（错误、缺失或被改动的内容）；
哪些是噪声、如何发现与处理，由你自己判断。说明依据与不确定性；此时不要求得出规律。

## 输入

`BRIEF.md`、`data/`、`TOOLS.md`。Python：`$python`。

$feedback

## 交付物

`stages/1_explore/notes.md`：看了什么、发现什么、哪些不确定。
可疑项写入 `knowledge/units.jsonl`，使用 `form=finding`、`status=inferred`；有直接依据的，用 `knosis knowledge evidence add` 记一条证据。
分析代码与工具结果放在 `stages/1_explore/`。

## 验收标准

笔记非空；知识单元结构检查通过，provenance 定位到数据文件的具体位置或反馈记录。
可疑项有统计量、约束、矛盾或反馈结果作为依据。完成后运行 `knosis ws check .`。
