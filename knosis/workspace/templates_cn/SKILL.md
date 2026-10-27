---
name: knosis
description: 在 Knosis 工作区或用户希望用 Knosis 分析数据、发现噪声、提取并验证可复用知识（含本体）时使用；不替代普通数据分析。
---

Knosis 提供可追溯的显式知识层，本会话的 agent 是执行者，不必启动另一个 agent。

**有名为 knosis 的 MCP 服务时**（`knosis install --kb` 装好的个人知识库）：开始一个不简单的任务前，调用一次
`knowledge_outline` 看知识体系，再用 `knowledge_select`（几个关键词，空格分隔）找与任务相关的知识；
inferred / contested 的知识是提示，用之前要核实。确实验证过、以后用得上的发现可以用 `knowledge_add` 记下；
其余不用手动记，会话结束后由 `knosis kb collect` 统一收集。

在含 `BRIEF.md` 与 `.knosis/state.json` 的工作区，读 BRIEF 与 AGENTS.md，
用 `knosis ws next .` 取得当前阶段的目标、输入、交付物和验收标准。
完成交付后运行 `knosis ws check .`；失败时依据问题修正。
阶段为 explore → extract → refine，refine 每轮验收保存快照；
用户决定结束改进时，用 `knosis ws goto . decide` 进入下游任务。

工作区外，用户需要这种流程时可运行
`knosis ws init <dataset> <scenario> --out <目录> [--kb <知识库>]`（`knosis list` 看支持的数据集）。
`knosis tool list` 与工作区的 `TOOLS.md` 提供可用工具（SQL、表画像、join 发现、方程拟合、ULTRA、TabPFN 等）。

知识层分两块：`kb/` 放知识（`kb/knowledge/units.jsonl`、`kb/knowledge/ontology/`、`kb/skills/`、`kb/outline.yaml`），
`evidence/` 放来源与验证（`evidence/ledger.jsonl`、`evidence/checks/`、`evidence/feedback/`）。
每条 κ 必有唯一 id、content、form、provenance、status。
form 为 finding/fact/rule/formula/schema/tool/procedure；status 为 observed/inferred/verified/contested/retracted/stale/merged。
粒度分两层：对象知识 instance / relation / dataset；元知识 method（怎么得到知识）/ usage（怎么用好知识，由反馈或消融支持）。
每次验证记一条证据（support/refute/undetermined/not_applicable）：可执行检查写进 `check` 后运行
`knosis knowledge verify`，其他用 `knosis knowledge evidence add`；verified 需要支持证据，被反驳要改状态。
用 `knosis knowledge select` 按任务挑知识（contested 默认不给），`knosis knowledge trace <id>` 看证据链；
有 `kb/outline.yaml` 时先用 `knosis knowledge outline` 看知识体系。
「如何运用知识解某类题」写成 `kb/skills/<名字>/SKILL.md`（讲怎么做）；它有没有效写成 usage 单元。
内化：重复的改为 merged + merged_into，矛盾的收窄条件 / 撤回 / superseded_by / conflicts_with + contested，
`knosis knowledge consolidate` 依次做去重、矛盾处理、构建知识体系；知识太多时 `knosis knowledge compact [--topic 主题]` 压缩。
记录 condition、derived_from 和验证支持数与反例数；来源定位到 data 文件的行、列、节点或边，
工具来源为 `tool:<name>@<version>(...)`，多来源用 ` ; ` 连接。
结构性知识可写成 `kb/knowledge/ontology/` 下的本体（OSI 标准三层），κ 用 `about` 引用本体元素。
工具输出 inferred 不是事实；撤回单元后将派生知识置为 stale 或 retracted。

不修改 `data/`；代码与笔记写入当前阶段目录。测试题只在 decide 出现，
不得寻找工作区外的测试 GT、不得运行 `knosis eval`，也不得把具体题目的答案提前缓存为知识。
