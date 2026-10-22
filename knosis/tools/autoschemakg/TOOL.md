---
name: autoschemakg
version: "0.1"
kind: program
modality: [text]
stage: [explore, extract]
license: "Apache-2.0（Knosis 自带）；抽取与概念化提示词取自 AutoSchemaKG（HKUST-KnowComp，MIT）"
---

把非结构化文本建成知识图谱，流程与 AutoSchemaKG（arXiv 2505.23628，NGD-Econ / NGD-MCP 的图即由它构建）一致：
1. 三元组抽取：每段文本抽三类三元组，实体—实体（Head / Relation / Tail）、事件—实体（Event / Entity）、
   事件—事件（before / after / at the same time / because / as a result）；
2. 概念化（schema 归纳）：给实体、事件、关系各写几个抽象概念，概念层就是归纳出的 schema，不需要预先定义。

**抽取由 agent 自己做**（你就是那个 LLM）：`prepare` 切段并写出提示词，你按 `PROMPTS.md` 为每段写一行
`extractions.jsonl`，再 `build`。也可以给 `--llm '<命令>'` 让工具逐段调用一个读 stdin 的命令自动抽取。

```bash
# 1. 切段，写 passages.jsonl 与 PROMPTS.md
knosis tool run autoschemakg -- prepare --text data/ --out stages/1_explore/kg --chunk-chars 3000
# 2. 按 PROMPTS.md 写 stages/1_explore/kg/extractions.jsonl（或：extract --llm 'claude -p' 自动抽取）
# 3. 建图：graph.graphml、nodes.csv、edges.csv、units.jsonl；并写 concept_todo.jsonl（待概念化的节点）
knosis tool run autoschemakg -- build --dir stages/1_explore/kg
# 4. 可选：按 concept_todo.jsonl 写 concepts.jsonl（每行 {"name", "type", "concepts": [...]}），再 build 一次得到 schema.json
knosis tool run autoschemakg -- build --dir stages/1_explore/kg
# 查询：某节点的邻居（名字子串匹配，不分大小写）
knosis tool run autoschemakg -- query --dir stages/1_explore/kg --node "PUMA" --hops 1
```

`extractions.jsonl` 每行与 AutoSchemaKG 输出同格式：
`{"id": "<段 id>", "entity_relation_dict": [{"Head", "Relation", "Tail"}], "event_entity_dict": [{"Event", "Entity": [...]}], "event_relation_dict": [{"Head", "Relation", "Tail"}]}`。
`build --extractions <文件>` 也能直接读上游的抽取文件（带 `original_text` 的行，如 NGD-Econ 的 `kg_extraction/*.json`）。

`edges.csv`（head, relation, tail, kind, passage, grounded）可以交给 `sql` 工具查询。
输出的 κ 全部是 inferred：一条图摘要（schema），每条实体三元组一条 finding（按头实体度数取前 `--max-units` 条），
有概念层时再加概念层的关系模式。来源写成 `data/<文件>#<start>-<end>`（与 text 评测同格式）。
`meta.grounded` 表示头尾实体是否在原段落里逐字出现；不出现的多半是改写或幻觉，采纳前要回原文核对。
