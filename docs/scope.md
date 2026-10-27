# Scope of Knosis

## In one sentence

Knosis is a **knowledge-centric** foundation for agents such as Codex and Claude Code: while an agent works on tasks over heterogeneous data,
it continually proposes, verifies and revises a **verifiable knowledge base**. Knosis manages the knowledge's format, evidence, verification, selection, inheritance and evaluation; it is not an agent itself.

## Two settings

The same knowledge layer (format, evidence, consolidation, selection, inheritance) serves two settings:

- **Personal agents**: knowledge accumulates from a person's agent sessions (Codex / Claude Code) into a personal knowledge base, which later sessions reuse over MCP
  (`knosis kb collect` -> consolidation -> `knosis install --kb`).
- **Enterprise tasks**: knowledge and understanding accumulate on concrete tasks (benchmarks, business data) through a workspace explore -> extract -> refine -> decide;
  after dev feedback, checks and tool verification, the knowledge is written back to a knowledge base and inherited by new tasks of the same kind. Benchmarks are both a means of verification and representative of this kind of task.

## Four principles

1. **Setting: heterogeneous data.** Graphs (NGDBench), single tables (TabArena), multiple tables / relational databases (RelBench, BI-Bench, KramaBench),
   mappings (Burr), equations / simulators (LLM-SRBench, NewtonBench), time series (AlphaBench), spreadsheets (SpreadsheetBench), agent traces (Who&When), text.
2. **Target: agents.** Embedded mode (the agent reads `AGENTS.md` / the skill and calls Knosis itself) or driver mode (Knosis launches the agent stage by stage).
   Knosis is not an agent and does not train models.
3. **Focus: knowledge-centric.** The agent does not just finish tasks; it iterates on knowledge while doing them:
   it uses results (dev feedback, tools, checks) to support or refute knowledge, narrows conditions, retracts what no longer holds, and distills methods into meta-knowledge.
4. **Requirement: verifiable, with correctness separate from usefulness.** Every piece of knowledge can be supported, refuted, judged undetermined or not applicable;
   correct knowledge is not necessarily useful for the task at hand, so selecting knowledge for a task is a separate step. Ontologies are one kind of knowledge.

## Knowledge vs. memory and skills

The criterion: **can it be refuted by evidence from the environment?** Only what can be refuted counts as knowledge.

| | memory | skill | knowledge (Knosis) |
| --- | --- | --- | --- |
| Content | What happened, what was seen | How to do something | Conditional assertions about the environment / data |
| True or false? | Only a record | Judged by whether it works | Yes; can be supported or refuted |
| Value criterion | Can be retrieved | Task success | Correctness and benefit measured separately |
| Relation to reader | Bound to one agent | Depends on the reader's ability | Truth independent of the reader, benefit depends on the reader |
| How it updates | Append | Rewrite | Evidence-driven: accept, narrow conditions, retract and propagate downstream |

The three overlap: memory and agent experience are candidate sources of knowledge; the steps for "how to discover a kind of knowledge" can be written as method meta-knowledge, which is likewise conditional and verifiable.
The difference is not the storage format but **whether there is evidence and status**.

Knosis manages both knowledge and skills, stored and evaluated separately: **knowledge is understanding of the environment, independent of the agent, and must be refutable by environmental evidence;
a skill is how to apply knowledge to a class of tasks (a procedure)**. "Whether it helps" is itself a refutable assertion, written as usage meta-knowledge:
**usage says whether it helps, a skill says how**. Skills build on knowledge (they cite ids of knowledge and usage units) and are added by the agent during RSI based on feedback;
a capable agent may not need them, but they are still recorded in the library.

## What the knowledge layer consists of: kb + evidence

| Part | Component | File | Role |
| --- | --- | --- | --- |
| **kb** (knowledge body) | knowledge | `kb/knowledge/units.jsonl` + `kb/knowledge/ontology/` | κ (content, form, scope, condition, provenance, status); ontologies are another way to store structured knowledge (OSI three layers), with elements expanded into `form=schema` κ |
| | skills | `kb/skills/<name>/SKILL.md` | How to apply knowledge to a class of tasks: conditions, cited knowledge, steps |
| | outline | `kb/outline.yaml` | Knowledge structure: links single-hop knowledge into "scenario -> relations between data -> specific objects" |
| | graph and flows | `kb/graph.json`, `kb/flows/` | Knowledge graph of objects and relations; flowcharts of task procedures |
| **evidence** (sources and verification) | ledger | `evidence/ledger.jsonl` | One entry per verification: support / refute / undetermined / not applicable, with method, source and fingerprints of the data it depends on |
| | check scripts | `evidence/checks/` | Executable checks that Knosis reruns and records as evidence |
| | feedback records | `evidence/feedback/` | Results on dev tasks, used as evidence sources |
| | traces | `evidence/traces/` | Collected sessions and other source material |
| | consolidation log | `evidence/consolidate.jsonl` | Operations performed by dedup, conflict resolution, organize, structure and compact |

kb holds only conclusions and evidence holds the process; a κ's `provenance` and `check` are just pointers into evidence.

**How knowledge was found, and how it is managed**: the units a piece of knowledge was derived from, the evidence that supports or refutes it, and the candidates that were retracted form its evidence chain
(`knosis knowledge trace`). Knosis manages this chain: the ledger, rerunning checks, status/evidence consistency checks, evidence expiry when data changes, and retraction propagation.

## Granularity: object knowledge and meta-knowledge

| Level | scope | What it is about | How it is verified |
| --- | --- | --- | --- |
| Object knowledge | instance | A specific object (row, node, edge, column) | Compare item by item against GT; query the data directly |
| Object knowledge | relation | Structure between objects (joins, ontology relations) | Inclusion dependency / foreign key checks; compare against GT relations |
| Object knowledge | dataset | Patterns, distributions, formulas of the data as a whole | Rerun checks on held-out rows / points |
| Meta-knowledge | method | How to **obtain** knowledge: methods for discovery and verification (steps only) | The script runs outside its original workspace and still produces valid results on new data |
| Meta-knowledge | usage | How to **use** knowledge well: which knowledge or skills help which tasks and readers | Dev feedback statistics, ablation (`ws fork --drop`) |

There is no "domain law" level: an assertion that holds across data can only be tested on several datasets of the same kind. A pattern verified on one dataset belongs to `dataset`;
what should transfer is written as `method`, and transfer happens by rerunning the method on new data, not by having new data trust an old pattern.

## Consolidation: no duplicates, no contradictions, organized

A knowledge base keeps growing: the same fact gets recorded by different sessions, new evidence overturns old conclusions, and knowledge goes stale when the environment changes. Consolidation is a set of operators on kb;
the agent judges content, Knosis checks invariants and logs to evidence: verify (rerun checks), dedup (`merged_into` aliases),
conflict (narrow conditions / decide by evidence / `superseded_by` version replacement / `conflicts_with` + contested),
organize (build the outline; induced higher-level patterns are new assertions that must state their sources and be verified again), structure (knowledge graph and flowcharts), and compact (merge units that can be stated together). The command is `knosis knowledge consolidate`.

## Across tasks: standalone knowledge bases

A knowledge base is independent of workspaces and is a git repository. A workspace inherits from it at the start (optionally only meta-knowledge) and writes back at the end; structure and evidence consistency are checked before write-back.
This makes "accumulation across tasks", "inheritance by a different agent" and "detecting stale knowledge after the environment changes" possible to test.

## Three evaluation measures

| Measure | What it tests | How |
| --- | --- | --- |
| Correctness | Whether the knowledge itself is right | Check in environments where the true knowledge is known: NGD noise assertions against the real noise; equations recomputed on held-out points; pattern checks rerun on held-out rows; ontologies against GT relations |
| Applicability / selection | Whether the selected knowledge fits here | `used_units`, single-unit ablation (`ws fork --drop`) |
| Benefit | Whether it helps the task | Controls with none / K_inherit / K_0 / K_final; controls with a different reader |

Cost is also reported: agent run time (`.knosis/runs.jsonl`).

## Out of scope

Training models; building an agent; hard GT isolation (isolation is soft: for formal evaluation, keep the raw data outside the agent's environment); LLM judging across all datasets.
