---
name: knosis
description: 在 Knosis 工作区或用户希望用 Knosis 分析数据、发现噪声、提取并验证可复用知识（含本体）时使用；不替代普通数据分析。
---

Knosis 提供可追溯的显式知识层，本会话的 agent 是执行者，不必启动另一个 agent。

在含 `BRIEF.md` 与 `.knosis/state.json` 的工作区，读 BRIEF 与 AGENTS.md，
用 `knosis ws next .` 取得当前阶段的目标、输入、交付物和验收标准。
完成交付后运行 `knosis ws check .`；失败时依据问题修正。
阶段为 explore → extract → refine，refine 每轮验收保存快照；
用户决定结束改进时，用 `knosis ws goto . decide` 进入下游任务。

工作区外，用户需要这种流程时可运行
`knosis ws init <dataset> <scenario> --out <目录>`；目前支持 NGDBench ngd-fin 与 TabArena。
`knosis tool list` 与工作区的 `TOOLS.md` 提供可用工具（SQL、表画像、join 发现、ULTRA、TabPFN）。

知识写入 `knowledge/units.jsonl`。每条必有唯一 id、content、form、provenance、status。
form 为 finding/fact/rule/formula/schema/tool；status 为 observed/inferred/verified/retracted/stale。
记录 condition、derived_from 和验证支持数与反例数；来源定位到 data 文件的行、列、节点或边，
工具来源为 `tool:<name>@<version>(...)`，多来源用 ` ; ` 连接。
结构性知识可写成 `knowledge/ontology/` 下的 Ossie 三文件本体，κ 用 `about` 引用本体元素。
工具输出 inferred 不是事实；撤回单元后将派生知识置为 stale 或 retracted。

不修改 `data/`；代码与笔记写入当前阶段目录。测试题只在 decide 出现，
不得寻找工作区外的测试 GT、不得运行 `knosis eval`，也不得把具体题目的答案提前缓存为知识。
