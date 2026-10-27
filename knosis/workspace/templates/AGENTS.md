# Knosis workspace

Read `BRIEF.md` first. Run `knosis ws next .` to get the goal of the current stage;
after finishing the deliverables, run `knosis ws check .` to run the acceptance check and commit a knowledge version.
If the command is not on PATH, use `$python -m knosis ...`.

## Directories and environment

- `data/`: read-only visible data; do not modify it.
- `tasks/dev.jsonl`: dev questions (no answers, no overlap with the test questions); submit with `knosis feedback submit <file>` to get feedback.
- `tasks/tasks.jsonl`: test questions without answers, present only in the decide stage.
- `stages/1_explore/`, `2_extract/`, `3_refine/round_<n>/`, `4_decide/`:
  code, notes and deliverables of the current stage.
The knowledge layer has two parts: `kb/` holds the knowledge itself (conclusions), `evidence/` holds sources and the verification process.

- `kb/knowledge/units.jsonl`: current knowledge, one κ per line.
- `kb/knowledge/ontology/` (optional): structured knowledge (ontology), the three OSI layers, see below.
- `kb/skills/<name>/SKILL.md`: usage procedures, how to apply knowledge to solve a class of tasks (optional, see below).
- `kb/outline.yaml` (optional): outline of the knowledge base, organized by the consolidation step.
- `evidence/ledger.jsonl`: evidence ledger, one verification result per line (write it with commands, do not edit by hand).
- `evidence/checks/`: executable check scripts for units (optional).
- `evidence/feedback/`: dev feedback records (read-only, written by `knosis feedback submit`).
- `.knosis/state.json`: stage state; historical knowledge snapshots are in `stages/<stage>/{kb,evidence}/`.

The data may contain noise; you decide what is noise and how to handle it, and write the basis for your judgment into knowledge.
Use `$python` for Python; pandas, pyarrow and other data dependencies are installed.
See `TOOLS.md` for available tools and how to call them. Tools only produce annotations; they do not modify data.
`inferred` in tool output does not mean verified; judge it and verify it on the data before adopting it.

## Knowledge unit κ

Required: `id` (unique string), `content`, `form`, `provenance`, `status`.
`form` (form of expression) is finding / fact / rule / formula / schema / tool / procedure (step-wise expression).
`status` is observed / inferred / verified / contested / retracted / stale / merged (merged is used only in dedup, see below).
Optional: `scope` (scope, see below), `condition` (conditions and exceptions), `derived_from` (list of parent unit ids),
`support` (number of independent supports), `about` (referenced ontology elements or data locations, e.g. `data/train.parquet#col/bmi`),
`check` (executable check, see below), `meta` (scores, counterexample counts, etc.).

`scope` has two layers. **Object knowledge** (about the environment): `instance` a specific object (row, node, edge); `relation` structure between objects
(join, ontology relation); `dataset` regularities, distributions and formulas of this data as a whole. **Meta-knowledge** (about knowledge): `method` how to **obtain** knowledge, i.e. the steps to discover or verify
a class of knowledge (write only the steps, write the conclusions separately as object knowledge; you may attach an executable check, and it can be followed on another dataset too); `usage` how to **make good use of** knowledge, i.e. which knowledge or
skills are effective for which kind of question and which reader (Knosis generates candidates automatically from dev feedback; it can only be supported by feedback or ablation evidence). If omitted, it is inferred automatically from form and source.

Provenance formats:

- Data: `data/graph.gpickle#node/<id>`, `data/graph.gpickle#edge/<src>|<label>|<dst>`,
  `data/train.parquet#row/<row_id>` or `#col/<column name>`.
- Tool: `tool:<name>@<version>(<k=v,...>)`.
- Feedback: `feedback:<record id>#item/<question id>`.
- Purely derived: `derived`; in this case `derived_from` is required.
- Join multiple sources with ` ; `. Merged knowledge keeps its parent units; after a retraction, mark affected descendants stale or retracted.

## Evidence and verification

Knowledge must be supportable or refutable by evidence. Record one piece of evidence per verification; the verdict is support / refute / undetermined (the condition or measurement cannot be confirmed) /
not_applicable (the premise does not hold):

- Executable check: the unit carries `check`, and Knosis reruns it and records evidence (`knosis knowledge verify [--unit ID]`).
  `{"kind": "sql", "query": "SELECT ... FROM train ...", "expect": [[...]]}` (table names are the file names under `data/`; without expect, it supports if the first row is all true),
  or `{"kind": "python", "path": "evidence/checks/<id>.py"}` (run from the workspace root; exit code 0 supports, 1 refutes, anything else is undetermined).
  Check scripts may only read `data/` and may only import code in `evidence/checks/`: knowledge will be inherited by other workspaces, which do not have your `stages/`.
  Checks with `scope=method` are trial-run during the extract / refine acceptance check in a temporary directory containing only `data/`, `kb/` and `evidence/`.
- Other verification: `knosis knowledge evidence add --unit ID --verdict support --method tool|data|feedback|ablation|derivation|human --source <source> --note "<numbers>" [--inputs data/...]`;
  import the `evidence.jsonl` written by tools with `knosis knowledge evidence import <file>`.

Status rules (checked by `ws check`): `verified` has at least one non-expired supporting piece of evidence; when the most recent decisive piece of evidence is a refutation,
the status must be contested, retracted or stale (it can be re-verified after you narrow the condition); `support: n` does not exceed the number of independent sources.
Evidence records the fingerprint of the data it depends on; when the data changes, the evidence expires. `knosis knowledge trace ID` outputs the evidence chain of a piece of knowledge.

## Consolidation: no duplicates, no contradictions, a coherent system

- **Dedup**: when two units say the same thing, keep the better one (merge sources and conditions), and change the other to `"status": "merged"` and add
  `"merged_into": "<primary unit>"` (it becomes an alias; references to it are resolved through the alias). Do not delete units.
- **Contradiction**: for mutually exclusive assertions about the same object, (1) narrow the condition so that each holds; (2) adjudicate with new evidence, and the overturned one becomes retracted; (3) the environment changed, so change the old one
  to stale and add `"superseded_by": "<new unit>"`. If you cannot adjudicate for now: both record each other in `"conflicts_with": [...]`, and at least one is contested
  (contested is not picked by `select` by default).
- **Build the knowledge system**: `kb/outline.yaml` links single-hop knowledge into a thread of "scenario → relations between data → specific objects"; write induced higher-level regularities as new units
  (`provenance: derived`, `derived_from` at least two, starting from inferred).
`knosis knowledge candidates` lists suspected duplicates and contradictions; `knosis knowledge consolidate` is run uniformly by the runner after refine.

## Selecting knowledge

Correct knowledge is not necessarily useful for the current task. `knosis knowledge select [--about <ontology element>] [--form F] [--text <keywords>]`
lists candidates (including ontology elements) with evidence counts; `--scope` filters by scope (`usage` shows which knowledge is useful for which kind of question);
`knosis knowledge index --prefix data/...` looks up related knowledge by object. You decide which to use, and record `used_units` in decide.
If the workspace inherited knowledge from a knowledge base (`stages/0_inherit/kb` exists), you must likewise judge per task whether it applies;
you may correct it, narrow it or retract it.

## skill: how to apply knowledge (solving procedure)

Knowledge is an understanding of the environment, independent of who uses it; a skill is a usage: when facing a kind of question, which steps to follow and which knowledge to call on to solve it.
**usage covers whether it is useful, skill covers how to do it**: a skill itself makes no claim of right or wrong; whether it is effective is written as a usage unit (`scope=usage`, `meta.of: skill:<name>`;
dev feedback automatically generates `usage/skill:<name>/<question type>`); do not record evidence directly on a skill.
When reviewing feedback, correctly answered questions can be summarized into effective solving methods, and wrongly answered questions into practices to avoid.
Write it in `kb/skills/<name>/SKILL.md` with a YAML header: `name` (same as the directory name), `description` (one sentence),
`when` (applicable question types and conditions), `uses` (referenced knowledge ids, including usage units), `derived_from` (which feedback records it was summarized from, optional),
`status` (active / stale / retracted); the body contains the steps. After referenced knowledge is retracted, the skill must be changed to stale or retracted.
`knosis knowledge skills` lists existing skills; skills used in decide are written as `skill:<name>` in `used_units`.

## Ontology (optional)

Structural knowledge can be written as an ontology, following the three layers of the OSI (Open Semantic Interchange, now Apache Ossie 0.2) standard: semantic model (tables / columns / primary keys / joins / measures),
concepts (concepts and relations between concepts), mapping (columns to concepts), placed at `kb/knowledge/ontology/<name>.{semantic_model,ontology,mapping}.yaml`
(multiple ontologies each take a subdirectory `kb/knowledge/ontology/<name>/`). Information the standard cannot express (conditions, scope, cardinality, source) goes in
`custom_extensions` (`vendor_name: EOB`, `data` is a JSON string); do not change the official schema.
Ontology elements are also knowledge (`form=schema`, ids like `ontology/[<subdirectory>/]join/<name>`); you can record evidence for, derive from or retract them;
a κ references ontology elements with `about: ["Product", "Sale.product", "sales.Amount"]`; `ws check` checks that references resolve,
and that each mapping `expression` is an existing `dataset.field`.
`python -c "from knosis.knowledge import ontology; help(ontology)"` has the format description and constructors.

## Boundaries

Do not search for, read or guess where the test GT is stored; do not run `knosis eval`. Files outside the workspace are irrelevant to this task.
Knosis is a knowledge layer, not a new agent; complete the stage in this session, and do not launch nested agents.
