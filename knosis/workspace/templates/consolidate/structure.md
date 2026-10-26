# 内化 4/4：结构化（知识图谱 + 流程图）

知识层根目录：`$base`（$n_units 条活跃 κ，$n_inactive 条已失效）。大纲 `kb/outline.yaml` 已在上一步整理好。
目标：把同一批知识再组织成两种结构，让人和 agent 能按「对象之间的关系」和「做事的步骤」来查：

- **知识图谱** `$base/kb/graph.json`：环境里有哪些对象（表、列、实体类型、变量、概念、指标、工具、任务……），
  它们之间是什么关系。每条边就是某几条单元说的那件事。
- **流程图** `$base/kb/flows/<名字>.json`：某类任务按什么步骤做、在哪里检查、在哪里分支，每一步用到哪条知识。
  来源是 procedure 单元、method 元知识与 skill。

现状：
$summary

$existing

## 输入

- `$base/kb/knowledge/units.jsonl`、`$base/kb/skills/*/SKILL.md`、`$base/kb/outline.yaml`、`$base/kb/knowledge/ontology/`；
  可用 `knosis knowledge select --ws $base`、`knosis knowledge outline --ws $base`、`knosis knowledge trace <id> --ws $base` 查看。

## 知识图谱的要求

1. 实体：`{"id", "type", "label", "units": [...], "description"}`。`id` 全图唯一，用 `类型:名字` 的形式（如 `table:orders`、
   `column:orders.amount`、`variable:mass1`、`concept:Customer`、`tool:tabpfn`、`task:driver-top3`）。`type` 优先取
   dataset / table / column / entity_type / variable / concept / metric / tool / task / file。`units` 列出描述这个对象本身的单元
   （如它的粒度、取值范围、分布、坑）。
2. 关系：`{"src", "rel", "dst", "label", "units": [...]}`。`rel` 用简短的英文动词短语（has_column、references、joins、
   derived_from、predicts、depends_on、measured_by、maps_to、contains、constrains……），`label` 写一句中文说明
   （如「cust_id，多对一」）。**每条关系至少引用一条活跃单元**，引用的单元必须真的说了这件事。
3. 只组织、不新增断言：图谱里出现的关系都要能在引用的单元里找到；单元没说过的关系不要画。不修改 `units.jsonl`、证据与 skill。
4. 覆盖：活跃的对象知识（$n_objects 条，instance / relation / dataset）至少 $graph_cov 要被某个实体或关系引用。
   规则（rule）与公式（formula）尽量挂到它们约束的对象上，网页会据此生成「规则 / 公式卡片」。
5. 本体（ontology）已经是结构化的，图谱里可以用相同的实体名，并在 `units` 里引用 `ontology/...` 单元。

## 流程图的要求

1. 每张流程图一个文件 `kb/flows/<名字>.json`：`{"name", "title", "goal", "nodes": [...], "edges": [...]}`。
2. 节点 `{"id", "kind", "text", "units": [...]}`，`kind` 取 start / step / check / decision / end；恰有一个 start、
   至少一个 end，所有节点从 start 可达；decision 至少两条出边，出边写 `label`（如「是」「否」「> 10%」）。
   step / check / decision 至少引用一条活跃单元或 `skill:<名字>`。
3. 边 `{"src", "dst", "label"}`。
4. 一张图讲一类任务或一个方法（例如「判断表的粒度」「从受控实验发现定律」「提交前自检」），一般 4 到 12 个节点；
   skill 的步骤、method 元知识、procedure 单元应当出现在某张流程图里。procedure / method / skill 共 $n_procedural 条，
   至少 $flow_cov 要被流程图引用。

## 验收

`knosis knowledge check --ws $base` 没有以 `structure` 开头的问题，且不新增其他问题$check_note；覆盖率达到上面的要求；
`knosis knowledge graph --ws $base` 可以看到摘要。最后用两三句话说明图谱的主干是什么、画了哪几张流程图。
