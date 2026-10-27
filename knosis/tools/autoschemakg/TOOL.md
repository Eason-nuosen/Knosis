---
name: autoschemakg
version: "0.1"
kind: program
modality: [text]
stage: [explore, extract]
license: "Apache-2.0 (bundled with Knosis); the extraction and conceptualization prompts come from AutoSchemaKG (HKUST-KnowComp, MIT)"
---

Builds a knowledge graph from unstructured text, following the AutoSchemaKG pipeline (arXiv 2505.23628; the NGD-Econ / NGD-MCP graphs were built with it):
1. Triple extraction: from each passage, extract three kinds of triples: entity–entity (Head / Relation / Tail), event–entity (Event / Entity),
   and event–event (before / after / at the same time / because / as a result);
2. Conceptualization (schema induction): write a few abstract concepts for each entity, event and relation. The concept layer is the induced schema; nothing has to be defined in advance.

**The agent does the extraction itself** (you are the LLM): `prepare` chunks the text and writes the prompts; following `PROMPTS.md`, you write one line of
`extractions.jsonl` per passage, then run `build`. Alternatively, `extract --llm '<command>'` calls a command that reads the prompt from stdin, once per passage and prompt, and writes `extractions.jsonl` automatically.

```bash
# 1. Chunk the text; writes passages.jsonl and PROMPTS.md (--overlap sets the chunk overlap, default 0)
knosis tool run autoschemakg -- prepare --text data/ --out stages/1_explore/kg --chunk-chars 3000
# 2. Write stages/1_explore/kg/extractions.jsonl following PROMPTS.md
#    (or extract automatically: extract --dir stages/1_explore/kg --llm 'claude -p' [--limit N])
# 3. Build the graph: graph.graphml, nodes.csv, edges.csv, units.jsonl; also writes concept_todo.jsonl (nodes to conceptualize)
knosis tool run autoschemakg -- build --dir stages/1_explore/kg
# 4. Optional: following concept_todo.jsonl, write concepts.jsonl (one {"name", "type", "concepts": [...]} per line),
#    or generate it with: conceptualize --dir stages/1_explore/kg --llm 'claude -p'
#    then build again to get schema.json
knosis tool run autoschemakg -- build --dir stages/1_explore/kg
# Query: neighbors of a node (case-insensitive name substring match)
knosis tool run autoschemakg -- query --dir stages/1_explore/kg --node "PUMA" --hops 1
```

Each line of `extractions.jsonl` has the same format as AutoSchemaKG output:
`{"id": "<passage id>", "entity_relation_dict": [{"Head", "Relation", "Tail"}], "event_entity_dict": [{"Event", "Entity": [...]}], "event_relation_dict": [{"Head", "Relation", "Tail"}]}`.
Items with missing or non-string fields (common in truncated LLM output) are skipped.
`build --extractions <file>` can also read an upstream extraction file directly (lines carrying `original_text`, such as NGD-Econ's `kg_extraction/*.json`);
those passages are numbered by line and their source is written as `<file>#line/<n>`.

`concept_todo.jsonl` lists the highest-degree entities and events (`--concept-limit`, default 100) plus the most frequent relations, each with context and a ready-made prompt.
`edges.csv` (head, relation, tail, kind, passage, grounded) can be queried with the `sql` tool.
All output κ are inferred: one graph summary (schema), one finding per entity triple (ranked by head-entity degree, deduplicated, top `--max-units`, default 200),
and, when a concept layer exists, the concept-level relation patterns (up to 20). Sources are written as `data/<file>#<start>-<end>` (the same format as the text evaluation).
`meta.grounded` tells whether both head and tail entities appear verbatim in the original passage; ones that do not are usually paraphrases or hallucinations, so check the original text before adopting them.
