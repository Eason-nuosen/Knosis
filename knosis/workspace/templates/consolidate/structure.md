# Consolidation 4/4: structuring (knowledge graph + flows)

Knowledge layer root: `$base` ($n_units active κ, $n_inactive inactive). The outline `kb/outline.yaml` was organized in the previous step.
Goal: organize the same knowledge into two more structures, so that people and agents can look it up by "relations between objects" and by "steps for doing things":

- **Knowledge graph** `$base/kb/graph.json`: which objects exist in the environment (tables, columns, entity types, variables, concepts, metrics, tools, tasks...),
  and what relations hold between them. Each edge is the thing that some units say.
- **Flows** `$base/kb/flows/<name>.json`: which steps a kind of task follows, where it checks, where it branches, and which knowledge each step uses.
  Sources are procedure units, method meta-knowledge and skills.

Current state:
$summary

$existing

## Inputs

- `$base/kb/knowledge/units.jsonl`, `$base/kb/skills/*/SKILL.md`, `$base/kb/outline.yaml`, `$base/kb/knowledge/ontology/`;
  you can inspect them with `knosis knowledge select --ws $base`, `knosis knowledge outline --ws $base`, `knosis knowledge trace <id> --ws $base`.

## Knowledge graph requirements

1. Entities: `{"id", "type", "label", "units": [...], "description"}`. `id` is unique across the graph, in the form `type:name` (e.g. `table:orders`,
   `column:orders.amount`, `variable:mass1`, `concept:Customer`, `tool:tabpfn`, `task:driver-top3`). `type` preferably takes
   dataset / table / column / entity_type / variable / concept / metric / tool / task / file. `units` lists the units describing this object itself
   (e.g. its granularity, value range, distribution, pitfalls).
2. Relations: `{"src", "rel", "dst", "label", "units": [...]}`. `rel` is a short English verb phrase (has_column, references, joins,
   derived_from, predicts, depends_on, measured_by, maps_to, contains, constrains...), `label` is a one-sentence plain-language description
   (e.g. "cust_id, many-to-one"). **Every relation references at least one active unit**, and the referenced units must really say this thing.
3. Only organize, add no assertions: every relation in the graph must be found in the units it references; do not draw relations the units never stated. Do not modify `units.jsonl`, evidence or skills.
4. Coverage: of the active object knowledge ($n_objects units, instance / relation / dataset), at least $graph_cov must be referenced by some entity or relation.
   Attach rules (rule) and formulas (formula) to the objects they constrain as much as possible; the web page uses this to generate "rule / formula cards".
5. The ontology is already structured; the graph may use the same entity names and reference `ontology/...` units in `units`.

## Flow requirements

1. One file per flow `kb/flows/<name>.json`: `{"name", "title", "goal", "nodes": [...], "edges": [...]}`.
2. Nodes `{"id", "kind", "text", "units": [...]}`, `kind` is one of start / step / check / decision / end; exactly one start,
   at least one end, all nodes reachable from start; a decision has at least two outgoing edges, and outgoing edges have a `label` (e.g. "yes", "no", "> 10%").
   step / check / decision reference at least one active unit or `skill:<name>`.
3. Edges `{"src", "dst", "label"}`.
4. One flow covers one kind of task or one method (e.g. "determine the granularity of a table", "discover a law from controlled experiments", "self-check before submission"), usually 4 to 12 nodes;
   the steps of skills, method meta-knowledge and procedure units should appear in some flow. There are $n_procedural procedure / method / skill items in total,
   and at least $flow_cov must be referenced by flows.

## Acceptance check

`knosis knowledge check --ws $base` has no problems starting with `structure` and introduces no other new problems$check_note; coverage meets the requirements above;
`knosis knowledge graph --ws $base` shows the summary. Finally, explain in two or three sentences what the backbone of the graph is and which flows you drew.
