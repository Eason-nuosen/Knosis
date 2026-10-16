## 目标

读懂数据的结构、分布与质量问题，重点发现噪声、异常、不一致和缺失，
说明依据与不确定性；此时不要求得出规律。

## 输入

`BRIEF.md`、`data/`、`TOOLS.md`。Python：`$python`。

## 交付物

`stages/1_explore/notes.md`：看了什么、发现什么、哪些不确定。
可疑项写入 `knowledge/units.jsonl`，使用 `form=finding`、`status=inferred`。
分析代码与工具结果放在 `stages/1_explore/`。

## 验收标准

笔记非空；知识单元结构检查通过，provenance 定位到数据文件的具体位置。
可疑项有统计量、约束或矛盾作为依据。完成后运行 `knosis ws check .`。
