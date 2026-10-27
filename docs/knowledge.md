# Knowledge layer format

The knowledge layer has two parts: **kb/** holds the knowledge itself (conclusions: permanent, inheritable, selectable), and **evidence/** holds the full record of sources and verification.
Workspaces and standalone knowledge bases share the same layout:

```
kb/
├── knowledge/
│   ├── units.jsonl               one κ per line: object knowledge + meta-knowledge
│   └── ontology/                 optional, structured knowledge: OSI standard (Apache Ossie 0.2) three layers + EOB extensions; one subdirectory per ontology
│       ├── <name>.semantic_model.yaml    semantic model: tables, columns, primary keys, joins, metrics
│       ├── <name>.ontology.yaml          concepts, relations between concepts, units and constraints (no tables or columns)
│       └── <name>.mapping.yaml           columns -> concepts / relations
├── skills/<name>/SKILL.md        optional, procedures: how to apply knowledge to a class of tasks
├── outline.yaml                  optional, knowledge outline (tree)
├── graph.json                    optional, knowledge graph: entities and relations, each citing units
└── flows/<name>.json             optional, flowcharts: steps, checks, decisions, each citing units or skills
evidence/
├── ledger.jsonl                  evidence ledger, one entry per line
├── consolidate.jsonl             consolidation log (dedup, conflict resolution, organize, structure, compact)
├── checks/<id>.py                optional, executable checks for units
├── feedback/<id>.json            feedback records on dev tasks
└── traces/                       source traces (sessions collected into a knowledge base, traces carried along on write-back)
```

`knosis migrate <dir>` converts a workspace or knowledge base in an older layout to this one.

For scope and positioning see [scope.md](scope.md).

Each time `ws check` passes in extract or refine, the whole knowledge layer (`kb/` and `evidence/`) is snapshotted to `stages/2_extract/` and
`stages/3_refine/round_<n>/`; these are K_0, K_1, ... Knowledge inherited from a knowledge base is in `stages/0_inherit/` (K_inherit). `ws fork --knowledge K_n`
copies the full layer of that version (a forked control has feedback disabled and compares only the given knowledge).

## κ units

```json
{"id": "income-pattern", "content": "conditional pattern in the training data", "form": "rule",
 "condition": "conditions under which it holds, and exceptions", "provenance": "data/train.parquet#col/MedianIncome",
 "status": "verified", "derived_from": [], "about": ["houses.MedianIncome"],
 "meta": {"support_count": 120, "counterexamples": 8}}
```

| Field | Required | Description |
| --- | --- | --- |
| `id` | yes | Unique within the workspace |
| `content` | yes | The knowledge (natural language / formula / triple text) |
| `form` | yes | Expression: `finding` / `fact` / `rule` / `formula` / `schema` / `tool` / `procedure` (step-wise) |
| `scope` | no | Granularity. Object knowledge: `instance` / `relation` / `dataset`; meta-knowledge: `method` (how knowledge is obtained) / `usage` (how to use knowledge well). If absent, `scope_of` infers it from form and provenance |
| `provenance` | yes | Source, see below |
| `status` | yes | `observed` / `inferred` / `verified` / `contested` (refuted, unresolved; not selected by default) / `retracted` / `stale` / `merged` (folded into another unit during dedup) |
| `condition` | no | Applicability conditions and known exceptions |
| `derived_from` | no | Parent unit ids |
| `support` | no | Number of independent supports |
| `about` | no | Anchored objects: ontology element names (must resolve when an ontology exists) or data locations `data/...#...`; `knosis knowledge index` looks units up by object |
| `check` | no | Executable check, see "Evidence" |
| `merged_into` | no | Dedup: the primary unit this one was merged into (status must be `merged`); derivations, skills and outlines that cite this unit resolve through the alias |
| `superseded_by` | no | Version replacement: the new unit that replaces this one after the environment changed (status must be `stale` / `retracted`) |
| `conflicts_with` | no | Identified, unresolved conflicts; if both sides are active, at least one must be `contested` |
| `meta` | no | Arbitrary extra information |

Provenance syntax: data `data/<file>#node/<id>`, `#edge/<src>|<label>|<dst>`, `#row/<row_id>`, `#col/<column>`;
tools `tool:<name>@<version>(<k=v,...>)`; feedback `feedback:<record id>#item/<task id>`; pure derivation `derived` (`derived_from` must be non-empty);
files in the knowledge layer `kb/...` / `evidence/...` (e.g. `evidence/traces/<id>.json#step/<n>`); join multiple sources with ` ; `.

Structural checks (`check_units`): required fields and allowed values, duplicate ids, `data/` and `kb/` / `evidence/` source files exist,
`feedback:` sources point to existing records, **I1** derivation references resolve (including historical versions), **I5** once a parent is retracted / stale,
its descendants must be `retracted` or `stale`; consistency of `merged_into` / `superseded_by` / `conflicts_with`.
Content is not judged. I2 (independent source count) is checked when evidence is given (see "Status agrees with evidence" below).

## Evidence

`evidence/ledger.jsonl` holds one verification per line:

```json
{"id": "e-0007", "unit": "smoker-rule", "verdict": "support", "method": "check", "source": "check:smoker-rule",
 "note": "rows=[[1]]", "inputs": {"data/train.parquet": "<size:mtime>"}, "created": "..."}
```

| Field | Values |
| --- | --- |
| `verdict` | `support` / `refute` / `undetermined` (condition or measurement cannot be confirmed) / `not_applicable` (premise does not hold; neither support nor counterexample) |
| `method` | `check` (Knosis reran the executable check) / `tool` / `data` / `feedback` / `ablation` (comparison without the knowledge) / `derivation` / `human` |
| `inputs` | Fingerprints of the data files the evidence depends on; if a file changes, the evidence expires and no longer counts |

Executable checks go in the unit's `check`: `{"kind": "sql", "query": ..., "expect": [[...]]}` runs on the tables in `data/`
(without `expect`, support means every value in the first row is true), or `{"kind": "python", "path": "evidence/checks/<id>.py"}` (exit code 0 supports, 1 refutes, anything else is undetermined).
`knosis knowledge verify` reruns checks and records evidence; other verification is recorded with `knosis knowledge evidence add` / `import` (an `evidence.jsonl` written by a tool).

**Status agrees with evidence** (`check_units(..., evidence=...)`): `verified` needs at least one unexpired support; if the latest decisive evidence refutes,
status must be `contested` / `retracted` / `stale`; **I2** `support: n` must not exceed the number of independent sources of supporting evidence (deduplicated by the part before `#`).
The agent still writes the status; Knosis only checks that it does not contradict the evidence.

**Evidence chain**: `knosis knowledge trace <id>` lists each unit along the derivation chain with its evidence, i.e. how the knowledge was found.
**Selection**: `knosis knowledge select [--about ...] [--form ...] [--scope ...] [--text ...]` filters for a task (including ontology elements) and attaches evidence counts; contested units are excluded unless `--include-contested`.

**Usage knowledge**: when a dev submission has a sibling `<file name>_used_units.jsonl` (one `{id, used_units}` per line), `feedback submit` computes, per task type, the dev accuracy of each knowledge unit / skill
"when used" vs. "when not used", and writes it as candidate κ with `scope=usage` (id `usage/<knowledge>/<task type>`, `meta.of` pointing to the evaluated item) plus feedback evidence.
A usage unit can only be `verified` by feedback or ablation evidence. The same statistics on test tasks go only into the evaluation report (`usage_effect` in `eval.json`), never back into the knowledge layer.

## Skills (procedures)

**Usage says whether it helps; a skill says how.** A skill is not true or false; its effect is written as a usage unit (`meta.of: skill:<name>`), and evidence is not recorded on the skill directly.

`skills/<name>/SKILL.md` uses the Codex / Claude Code skill format, with YAML front matter:

| Field | Description |
| --- | --- |
| `name` | Same as the directory name |
| `description` | One sentence |
| `when` | Applicable task types and conditions |
| `uses` | Referenced knowledge ids (κ or ontology units) |
| `derived_from` | Feedback records it was summarized from (optional) |
| `status` | `active` / `stale` / `retracted` |

Checks: `uses` resolves; once a used unit is retracted or stale, the skill must be `stale` / `retracted`; `derived_from` points to existing feedback records.
Its effect is in the usage units that evaluate it (`knosis knowledge skills` lists them together); decisions cite it as `skill:<name>` in `used_units`. Skills are not recorded per agent.

## Consolidation: dedup, conflict resolution, organize, structure

`knosis knowledge consolidate [--steps dedup,conflict,organize,structure]` launches an agent for each of the four steps in turn; `knosis knowledge candidates`
lists likely duplicates (similar content, same anchored object), possible conflicts (related units on the same object) and contested units, as hints only.

| Step | What the agent does | What Knosis checks |
| --- | --- | --- |
| dedup | Keeps one unit per fact (merging sources and conditions); the other becomes `merged` + `merged_into` | Aliases resolve to active units; no units deleted; no new issues |
| conflict | (1) narrow conditions; (2) decide with new evidence, retracting one side; (3) if the environment changed, mark the old one stale + `superseded_by`; pairs that cannot be decided record each other in `conflicts_with` and are marked contested | When both sides of `conflicts_with` are active, at least one is contested; no units deleted |
| organize | Links single-hop knowledge into a "scenario -> relations between data -> specific objects" outline in `kb/outline.yaml`; may add induced units | Outline references exist and every active unit is placed; induced units have `provenance: derived` and at least two `derived_from` |
| structure | Organizes the same knowledge into a knowledge graph `kb/graph.json` and flowcharts `kb/flows/*.json` | No unit changes; every edge and flow node cites active units; the graph cites >= 60% of active object-knowledge units, flowcharts cite >= 60% of procedure / method units and skills |

If a step fails acceptance it is retried once with the issues; if it still fails, `kb/` and `evidence/` are restored to their state before the step. On success, units before and after are compared and the
operations (add / induce / merge / supersede / status / conflict / narrow / condition / rewrite) are appended to `evidence/consolidate.jsonl`.
`knosis kb collect` runs consolidation automatically after collecting; `knosis ws run --consolidate` runs it once after refine and snapshots the result as a new refine version (K_final).
For the outline format see [interfaces.md](interfaces.md); `knosis knowledge organize` runs only the organize step.

### Compaction

Run on its own as the knowledge base grows; not part of the default steps:

```bash
knosis knowledge compact --ws ~/kb                            # the agent decides what to compact and how
knosis knowledge compact --ws ~/kb --topic "orders primary key"   # only compact knowledge related to this topic
```

The agent writes a group of units that can be stated together (scattered assertions about one object, several instances of one pattern, the same fact worded differently) as one primary unit
(merging conditions, exceptions and sources); the rest of the group become `merged` + `merged_into`. With `--topic`, Knosis first lists units matching the topic terms;
the agent decides which are really relevant, adds any that were missed, and touches only those. Knosis checks: the active unit count drops (no change at all also passes), every unit made inactive in this step
has `merged_into` or `superseded_by` pointing to an active unit, no units deleted, no new issues; on failure it retries once, then rolls back.
The record (including topic and active unit counts before and after) is appended to `evidence/consolidate.jsonl`. Equivalent to `consolidate --steps compact`.

### Forms of the knowledge structure

The same knowledge units (κ, skills, ontology units) can be organized in five ways. All of them only organize and add no assertions; every node, edge and step cites the units it comes from:

| Form | File | Produced by | Answers |
| --- | --- | --- | --- |
| Outline (tree) | `kb/outline.yaml` | agent (organize) | What blocks the knowledge falls into and what each covers |
| Knowledge graph | `kb/graph.json` | agent (structure) | Which objects exist in the environment and how they relate |
| Flowchart | `kb/flows/<name>.json` | agent (structure) | For a task type: which steps, where to check and branch, which knowledge each step uses |
| Derivation graph | computed (`derived_from` / `merged_into` / `superseded_by` / `conflicts_with`) | Knosis | Which knowledge is derived from, merged into or replaced by which; retraction propagates along it |
| Rule / formula cards | computed (rule and formula units grouped by graph entity) | Knosis | Which rules and formulas hold on each object |

```json
// kb/graph.json
{"entities": [{"id": "table:orders", "type": "table", "label": "orders", "units": ["extract/orders-key"]}],
 "relations": [{"src": "table:orders", "rel": "references", "dst": "table:customers", "label": "cust_id, many-to-one",
                "units": ["extract/orders-fk"]}]}
// kb/flows/find-grain.json
{"name": "find-grain", "title": "Determine the grain of a table", "goal": "...",
 "nodes": [{"id": "start", "kind": "start", "text": "Get a new table"},
           {"id": "count", "kind": "step", "text": "Group by candidate key and count", "units": ["method/grain-check"]},
           {"id": "dup", "kind": "decision", "text": "Duplicates?", "units": ["extract/orders-key"]},
           {"id": "end", "kind": "end", "text": "Record the grain"}],
 "edges": [{"src": "start", "dst": "count"}, {"src": "count", "dst": "dup"}, {"src": "dup", "dst": "end", "label": "no"}]}
```

Entity `id`s are unique in the graph (`type:name`); suggested `type`s are dataset / table / column / entity_type / variable / concept / metric / tool / task / file.
Every relation cites at least one active unit and its endpoints must exist; an entity without citations must be an endpoint of some edge. A flowchart has a title, at least three nodes,
exactly one start and at least one end; every node is reachable from start, each decision has at least two outgoing edges, and step / check / decision nodes cite at least one active unit or `skill:<name>`.
`knosis knowledge check` enforces these rules (issues start with `structure`); when a cited unit is retracted, stale or merged, the next structure step updates it.
View with `knosis knowledge graph [--view summary|graph|flows|derivation|cards] [--entity <entity>] [--depth N]`; the MCP tool `knowledge_graph` returns the subgraph around an entity.
The knowledge graph and flowcharts are copied only when a knowledge base is inherited in full; on partial inheritance the new workspace's structure step rebuilds them.

## Standalone knowledge base

`knosis kb init <dir>` creates one (a git repository with the layout above). `knosis ws init ... --kb <dir> [--kb-scope method,usage,skill]` inherits from it (optionally only some scopes;
ontologies come with `relation` / `dataset`, skills with `skill` or `usage`).
On the same dataset, tasks that appear in the knowledge base's feedback records are excluded from the new workspace's test set. `knosis kb merge <ws> --kb <dir> [--namespace <prefix>]` writes back:
κ are merged by id, evidence is appended, feedback records are renamed `<workspace>.<id>` with references rewritten; the whole knowledge base is checked after the merge and the merge is rejected if it fails.
`--namespace` prefixes unit ids (and skill names, check script paths) when merging workspaces from different datasets, so same-named ids do not overwrite each other.
`knosis kb import-ontology <annotation dir> --kb <dir> [--strip-gt]` imports an existing ontology (e.g. ontology-bench annotations) into `kb/knowledge/ontology/<unit name>/`;
`--strip-gt` removes the parts derived from benchmark GT.

## Ontology (structured knowledge)

Knosis supports the OSI (Open Semantic Interchange) standard as implemented by Apache Ossie, for summarizing, collecting and aligning knowledge about enterprise data at the ontology layer.
The format matches ontology-bench's EOB 0.2: the base is Apache Ossie `0.2.0.dev0`, and
benchmark-specific information always goes into `custom_extensions` (`vendor_name: EOB`, `data` is a JSON string), leaving the official schema untouched.
Field syntax is documented in ontology-bench's `docs/ontology-format-ossie.md`; `tests/fixtures/sales_bi/` is a complete example.

**Citable names** (`ontology.refs`): dataset names, `dataset.field`, core relationship names, metric names,
concept names, `concept.relation`. A κ's `about` uses these names to attach knowledge to ontology elements.

**Checks** (`check_ontology`, the parts the official `validate.py` does not cover): core relationship tables and columns exist and both sides have the same number of columns;
concept `extends` and relationship roles point to existing concepts or built-in types; mapping concepts exist, `expression` is an existing `dataset.field`,
and EOB `annotations` targets exist. For official JSON Schema validation use `validate.py` from the Ossie repository.

**κ view** (`ontology_units`): each dataset, core relationship, metric, concept and concept relation expands into a κ with `form=schema`;
`provenance` points to the location in the ontology file, and `status` follows the EOB `provenance.method`:
`human` / `annotator` -> verified, `converted` -> observed, `llm` / `tool` -> inferred.

**Construction**:

| Function | Purpose |
| --- | --- |
| `from_tables(name, tables, primary_keys, relationships)` | Build the core layer from DataFrames or {column: type} |
| `from_bibench(ds)` | Power BI metadata of a BI-Bench case (`_tables/_columns/_relationships`) -> core layer; drops auto date tables and RowNumber columns, keeps DAX for calculated columns, converts relationship direction to Ossie's many -> one, writes cardinality / active / filter direction to EOB |
| `from_relbench(ds)` | pkey / fkeys / time_col from a RelBench manifest -> core layer |
| tool `joins --ontology DIR` | Writes candidate primary keys and joins discovered in the data as a draft core layer (`method: tool`) |

Note: BI-Bench `_relationships` and RelBench foreign keys are GT in join-discovery / ontology-construction evaluations and must not be given to the agent under test.

## Dev feedback

The agent is Codex / Claude Code itself: Knosis does not record its trajectory; it only returns **results**, and the agent turns results into knowledge.

- Each workspace has a dev split (`tasks/dev.jsonl`, no answers, disjoint from the test tasks). The agent answers some or all dev tasks in the decide deliverable format;
  `knosis feedback submit <file>` returns per-task results and writes a record to `evidence/feedback/<id>.json`.
- Modes (`ws init --feedback`): `answer` returns correctness, score and the correct answer; `score` returns only correctness and score; `none` disables feedback. `--budget` caps the number of submissions;
  `--feedback-full` requires every submission to answer all dev tasks.
- Feedback accepts only dev ids; GT is read from the raw data directory, and the scorer is the same function as `knosis eval` (`score(..., ids)` in the `decision` layer).
- **Automatic RSI**: in driver mode, `knosis ws run <ws> --stage refine --rounds N` submits each round's
  `stages/3_refine/round_<n>/dev_<deliverable file>` automatically at the end of the round, and the result goes into the next round's prompt.
- The prompt only says the data may contain noise; what is noise, how to handle it and what the feedback means are left to the agent, which writes them as κ
  (e.g. "this edge is noise" is a finding whose provenance points to the feedback record and the data location).
