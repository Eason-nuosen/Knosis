# Architecture

Knosis is not an agent. It is the layer a coding agent (Codex, Claude Code) uses to produce and use explicit knowledge:
an auditable knowledge layer, tools the agent can call, and evaluation that shows whether the knowledge helps.
The agent decides how to analyze data; Knosis sets goals, keeps the record, and checks structure.

## Four layers and the workspace

| Layer | Package | Role |
| --- | --- | --- |
| Data | `knosis/data/` | One entry point, `load_dataset(name, scenario)`, returning a `Dataset` (tasks with GT, files, schema). Loaders in `data/loaders/`, agent-facing cards in `data/cards/`, `knosis download`. Agent traces are normalized to ATIF v1.7 (`data/traces.py`). |
| Knowledge | `knosis/knowledge/` | Storage and checks for knowledge units, evidence, ontology, skills, outline and structured views; consolidation; standalone knowledge bases. |
| Tools | `knosis/tools/` | One directory per tool (`TOOL.md` + `run.py`), run as a separate process. Current tools: `sql`, `profile`, `joins`, `fit`, `sheet`, `newton`, `autoschemakg` (programs) and `ultra`, `tabpfn` (models). |
| Decision | `knosis/decision/` | One scorer per dataset; `knosis eval` and dev feedback both call it. Also reports how decisions cited knowledge. |

The **workspace** (`knosis/workspace/`) ties the layers together for one dataset scenario. It is a git repository:

```
<ws>/
├── BRIEF.md  AGENTS.md  CLAUDE.md  TOOLS.md
├── data/                 visible data (read-only; hard links or copies, never symlinks)
├── tasks/dev.jsonl       dev tasks without answers, for feedback
├── tasks/tasks.jsonl     test tasks without answers, written only when decide starts
├── stages/{0_inherit, 1_explore, 2_extract, 3_refine/round_<n>, 4_decide}/
├── kb/                   current knowledge
├── evidence/             provenance and verification
└── .knosis/state.json    stage, round, options, feedback settings
```

## Data flow

1. **Data entry.** `knosis ws init <dataset> <scenario>` loads the raw dataset and calls the dataset's exporter, which writes the
   visible part to `data/`, a `BRIEF.md` (what the data is, what the downstream tasks look like, a few holdout examples without answers),
   and the dev / test split. `TOOLS.md` lists tools matching the exporter's modalities. `--kb <dir>` inherits knowledge from a
   standalone knowledge base (snapshot `K_inherit`).
2. **Agent + tools.** The agent works stage by stage: `explore → extract → refine (N rounds) → decide`. Each stage prompt states a goal,
   inputs, deliverables and acceptance criteria, not steps. The agent writes code, calls tools (`knosis tool run`), and submits dev
   answers with `knosis feedback submit` (modes `answer`, `score`, `none`; a submission budget).
3. **Knowledge layer.** Results go to `kb/` (units, ontology, skills) and `evidence/` (ledger, executable checks, feedback records, traces).
   `knosis ws check` validates the stage; on success it snapshots `kb/` + `evidence/` (`K_0` after extract, `K_n` after refine round n)
   and commits.
4. **Consolidation.** `knosis knowledge consolidate` (or `ws run --consolidate` after the last refine round) runs agent steps
   `dedup → conflict → organize → structure`. Each step is checked; a failing step is retried once with the issues, then rolled back.
   Operations are logged to `evidence/consolidate.jsonl`. In a driven run the result is snapshotted as a further refine version (`K_final`).
5. **Decisions and evaluation.** decide writes predictions (plus optional `used_units.jsonl`). `knosis eval` scores them against GT read
   from the raw data directory and writes `.knosis/eval.json`: task metrics, a trivial reference, knowledge usage, a knowledge summary,
   an optional knowledge-correctness score, and test-time usage effect (reported only, never written back).
   `knosis ws fork --knowledge none|K_inherit|K_0|K_<n>|K_final [--drop ids]` makes control copies that only run decide, with feedback off.
6. **Across tasks.** `knosis kb merge` writes a workspace's knowledge and evidence back to a standalone knowledge base (a git repo with the
   same `kb/` + `evidence/` layout); `knosis kb collect` extracts knowledge from recent Codex / Claude Code sessions into it.

## The knowledge-centric loop

| Phase | Where it happens |
| --- | --- |
| **Discovery** | explore and extract: findings, facts, rules, formulas, schema and ontology, each with condition and provenance; tool outputs enter as `inferred` / `observed` annotations. |
| **Internalization** | refine rounds (re-verify, narrow conditions, retract, derive) and consolidation (dedup, conflict handling, outline, knowledge graph and flowcharts). |
| **Use** | decide, `knosis knowledge select`, skills, and the MCP server; usage is measured from `used_units` on dev (written as `scope=usage` units) and test (eval report only). |

## Knowledge unit

κ = (content, form, condition, provenance, status), stored one per line in `kb/knowledge/units.jsonl` with an `id` and optional
`derived_from`, `support`, `about`, `check`, `scope` and alias fields. See [knowledge.md](knowledge.md) for the full format.

- **form**: `finding`, `fact`, `rule`, `formula`, `schema`, `tool`, `procedure`.
- **status**: `observed`, `inferred`, `verified`, `contested`, `retracted`, `stale`, `merged`.
- **scope**: object knowledge (`instance`, `relation`, `dataset`) or meta-knowledge (`method`, `usage`).
- **provenance**: a data location (`data/<file>#row/...`), a tool call (`tool:<name>@<version>(...)`), a feedback record, or `derived`.

Structural checks (`check_units`): required fields and values, unique ids, sources that resolve, I1 (derivation references resolve,
including past versions), I2 (`support` does not exceed independent supporting sources), I5 (descendants of an inactive unit are
retracted or stale), and status consistent with evidence (`verified` needs live support; a latest refutation forces contested,
retracted or stale). Evidence records data fingerprints and expires when the data changes.

## Ground-truth soft isolation

- GT never enters the workspace: exporters write only visible data and tasks without answers; test tasks appear only at decide.
- Files are hard-linked or copied, not symlinked, so the raw directory (where GT usually sits) is not exposed.
- Exporters strip leaking fields; for example, NGDBench keeps only attribute keys present in the clean graph.
- Dev feedback and evaluation load GT from the raw data directory, not from the workspace. On the same dataset, tasks seen in an
  inherited knowledge base's feedback are excluded from the new test set.
- `knosis eval` refuses to run inside a driven agent run (`KNOSIS_DEPTH >= 1`), and the MCP server does not expose evaluation.

This is soft isolation: the agent runs on the same machine as the raw data and could read it directly.

## Driver mode and embedded mode

| Mode | Who leads | How |
| --- | --- | --- |
| Driver | a person or script | `knosis ws run <ws> --agent {codex,claude} --stage ... --rounds N [--consolidate]` launches `codex exec` or `claude -p` per stage, runs the acceptance check, retries once with the issues, logs to `.knosis/runs.jsonl`, and submits each refine round's dev predictions automatically. Nested driven runs are refused (`KNOSIS_DEPTH`). |
| Embedded | the agent in the user's session | `knosis install` puts the Knosis skill into the Codex / Claude Code skill directories; the agent calls `knosis ws next` and `knosis ws check` itself. `knosis mcp --ws <dir>` exposes knowledge and tool operations over MCP; `knosis install --kb <dir>` registers it for Codex and prints the Claude Code command. |

## Design principles

- **Knosis checks structure, not content.** The agent writes status and judges correctness; Knosis checks that status, evidence,
  derivations and references are consistent.
- **Condition and provenance are recorded at write time.** They cannot be reconstructed later.
- **Discovered is not verified.** Tool outputs are `inferred` or `observed`; `verified` requires recorded supporting evidence.
- **Knowledge is retractable.** Units are never deleted: they are retracted, superseded or merged, and retraction propagates to descendants.
- **Tools annotate, never modify data.** Heavy models run in their own interpreter (`KNOSIS_<NAME>_PYTHON`); the core package does not
  import them.
- **Goals, not steps.** Stage templates are shared across datasets; how to reach the goal is left to the agent.
- **No test tasks during extraction.** Knowledge extracted from known test questions is a cache, not knowledge.
