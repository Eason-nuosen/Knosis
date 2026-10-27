# Knosis

> Knosis = knowledge + gnosis. **A knowledge substrate for agents: collect, manage and reuse what your agents learn.**

English | [中文](https://github.com/Eason-nuosen/Knosis/blob/main/README_CN.md)

**Live demo**: https://eason-nuosen.github.io/Knosis/

Knosis is not an agent. It lets coding agents such as Codex and Claude Code write down what they learn while working as
**explicit knowledge**: every piece of knowledge has a source, the conditions under which it holds, and evidence, so it can
be checked, traced and retracted; the next time the agent works, it retrieves what it needs.

Two scenarios, one knowledge layer:

- **Personal agents**: collect knowledge from your everyday Codex / Claude Code sessions into a personal knowledge base;
  new sessions use it through MCP.
- **Tasks and enterprise data**: on concrete tasks (benchmarks, business data) the agent accumulates knowledge as it
  explores; knowledge verified by evidence is written back to the knowledge base and can be inherited by similar tasks.

## Core concepts

- **Knowledge unit κ**: one piece of knowledge = content, form (fact / rule / formula / procedure ...), conditions, source
  and status (observed → inferred → verified, or contested / retracted / stale / merged). Stored in `kb/knowledge/units.jsonl`.
- **Evidence**: records that support or refute a unit (executable checks, tool output, dev feedback, trace steps), stored in
  `evidence/`. A unit's status must agree with its evidence.
- **Consolidation**: as knowledge grows, the agent deduplicates it, resolves contradictions, organizes it into a knowledge
  system (outline, knowledge graph, flows), and compacts it when it gets too large. Knosis checks every step, rolls back
  steps that fail, and logs what was done.
- **Workspace**: the full pipeline for one task, explore → extract → refine (corrected with dev feedback) → decide. Each stage
  is checked and committed to git; ground truth never enters the workspace.

Knowledge bases and workspaces share the same layout (`kb/` + `evidence/`). Both are local git repositories with one
commit per write-back, so every version can be restored.

## Installation

```bash
pip install knosis               # Python 3.10+
pip install 'knosis[all]'        # plus the dependencies some datasets need (networkx, h5py, openpyxl, downloaders)
```

You also need a coding agent: [Codex CLI](https://github.com/openai/codex) or [Claude Code](https://claude.com/claude-code);
both are tested. From source: `git clone`, then `pip install -e '.[all]'`; run the tests with `pytest -q`.

## Quick start: personal knowledge base

No dataset required.

```bash
knosis kb init ~/kb                                  # create the knowledge base (a local git repository)
knosis install --kb ~/kb                             # let Codex / Claude Code use it, see the next section

# work with your agent as usual; in a new session it first reads the outline, then searches for the task at hand

knosis kb collect --kb ~/kb --since 1d --dry-run     # see which sessions would be collected
knosis kb collect --kb ~/kb --since 1d               # extract → check → consolidate → commit a version (--source claude for Claude Code sessions)

knosis knowledge outline --ws ~/kb                   # the knowledge system
knosis knowledge select  --ws ~/kb --text <keyword>  # search
knosis knowledge trace <id> --ws ~/kb                # where a unit came from and its evidence
```

Only knowledge the environment can confirm or refute is collected (project conventions, data pitfalls, how tools and
commands actually behave, errors and their fixes, reusable methods), not preferences or chat. Session transcripts are
copied into the knowledge base for traceability, so **do not push your knowledge base to a public remote**.

## Using Knosis from Codex and Claude Code

Knosis connects to agents through two things: a **skill** (tells the agent the knowledge base exists, when to consult it
and how to write back) and an **MCP server** (`knosis mcp`, 16 tools to query and write knowledge inside a session).
`knosis install --kb ~/kb` installs both:

| | Codex | Claude Code |
| --- | --- | --- |
| skill | copied to `~/.codex/skills/knosis/` and `~/.agents/skills/knosis/` | copied to `~/.claude/skills/knosis/` |
| MCP | written into `~/.codex/config.toml` (a marked block, safe to re-run; tool calls pre-approved) | prints a command to run once: `claude mcp add -s user knosis -- <python> -m knosis.cli mcp --ws ~/kb` |
| one agent only | `knosis install --codex --kb ~/kb` | `knosis install --claude --kb ~/kb` |

In a new session the agent first reads the outline (`knowledge_outline`), then searches for the task (`knowledge_select`).
You can also just ask it to "look up what the knowledge base says about X" or "record this finding in the knowledge base".

**Collection** does not happen inside sessions; run it periodically (e.g. from cron):

```bash
knosis kb collect --kb ~/kb --since 1d                                  # Codex sessions (~/.codex/sessions)
knosis kb collect --kb ~/kb --since 1d --source claude                  # Claude Code sessions (~/.claude/projects)
knosis kb collect --kb ~/kb --since 1d --agent claude --model <model>   # use Claude Code for extraction (default: Codex)
```

Try the MCP server without a global install:

```bash
codex exec -c 'mcp_servers.knosis.command="knosis"' -c 'mcp_servers.knosis.args=["mcp","--ws","/abs/path/kb"]' \
  -c 'mcp_servers.knosis.default_tools_approval_mode="approve"' "<task>"
claude -p "<task>" --mcp-config '{"mcpServers":{"knosis":{"command":"knosis","args":["mcp","--ws","/abs/path/kb"]}}}' \
  --allowedTools mcp__knosis
```

Every command that runs an agent (`ws run`, `kb collect`, `knowledge consolidate / compact`) takes `--agent codex|claude`,
`--model` and `--effort`.

## Quick start: task workspace

```bash
knosis ws init tabarena houses --out ws/houses       # export a workspace from a dataset (data entries below)

# driver mode: Knosis runs the agent through every stage, checks each one and retries once on failure
knosis ws run ws/houses --agent codex --stage explore extract refine decide --rounds 2 --consolidate
knosis ws run ws/houses --agent claude --model <model> --effort medium ...   # with Claude Code

# embedded mode: open the workspace in your agent (Codex reads AGENTS.md, Claude Code reads CLAUDE.md) and let it proceed
knosis install

knosis eval ws/houses                                # evaluate, writes .knosis/eval.json
knosis ws fork ws/houses --out ws/houses-none --knowledge none   # ablation: no knowledge / K_0 / K_final
```

Ground truth is only read at evaluation time, test tasks are generated only at decide, and feedback only accepts dev tasks.
This is soft isolation, not a security boundary: for formal evaluations keep the raw data outside the agent's environment.

## Managing knowledge

```bash
knosis knowledge check       --ws <dir>                    # structure, sources, status vs. evidence
knosis knowledge consolidate --ws <dir>                    # deduplicate → resolve contradictions → organize → structure
knosis knowledge compact     --ws <dir> [--topic <topic>]  # shrink a large base: agent decides what to merge, or only one topic
knosis mcp --ws <dir>                                      # expose the knowledge layer and tools over MCP (16 tools)
```

Merged or compacted units are never deleted; they stay as aliases of the unit that covers them. When a unit is retracted,
the units derived from it must be invalidated too (the check reports them).

## Knowledge system: multiple forms, stored and visualized

Knowledge is more than a list. Consolidation organizes the same units into several forms, each answering a different
question. All of them are files in the knowledge base, and every node, edge and step cites the units it comes from
(no new claims are added; Knosis checks the citations):

| Form | Stored as | Answers | Produced by |
| --- | --- | --- | --- |
| Outline (tree) | `kb/outline.yaml` | what parts the knowledge falls into and what each covers: scenario → relations between data → objects | agent (organize) |
| Knowledge graph (KG) | `kb/graph.json` | which objects exist (tables, columns, variables, concepts, tools ...) and how they relate | agent (structure) |
| Flows | `kb/flows/*.json` | how a kind of task is done: steps, checks, branches, and which unit or skill each step uses | agent (structure) |
| Derivation graph | computed from `derived_from` / `merged_into` / `superseded_by` | which units were derived from, merged into or superseded by which; retractions propagate along it | computed by Knosis |
| Rule and formula cards | computed from rule / formula units | which rules and formulas hold on each object | computed by Knosis |
| Ontology (OSI standard) | `kb/knowledge/ontology/` | structured semantics of the data: entities, attributes, relations, keys | agent, or imported from BI / database metadata |

Knowledge bases from several datasets can be merged into one (`knosis kb merge --namespace`) and consolidated again to
find entities and knowledge shared across datasets.

Viewing and visualization:

```bash
knosis knowledge outline --ws <dir>                       # outline rendered as markdown
knosis knowledge graph   --ws <dir>                       # summary of the knowledge graph and flows
knosis knowledge graph   --ws <dir> --entity <entity> --depth 2   # subgraph around one entity, edges with their units
knosis knowledge graph   --ws <dir> --view flows|derivation|cards
```

Agents read the same content through the MCP tools `knowledge_outline` and `knowledge_graph`.
The [live demo](https://eason-nuosen.github.io/Knosis/) renders the knowledge graphs, flows, derivation graphs, cards and
outlines of each dataset as interactive pages, plus an atlas merged from several datasets; the site is generated from the
demo workspaces by `site/build.py`.

## Supported data

Knosis targets **heterogeneous data**: one knowledge layer (κ + evidence + ontology) covers the data types below, each with
evaluable data entries and matching tools.

| Data type | Data entries | Knowledge the agent derives | Tools |
| --- | --- | --- | --- |
| Single table | tabarena (classification / regression on 51 tabular datasets) | column meanings, distributions and outliers, feature–target relations, modeling lessons | profile, sql, fit, tabpfn |
| Spreadsheets | spreadsheetbench (cell / sheet manipulation on real xlsx files) | workbook structure, how formulas and operations actually behave | sheet (inspect structure, recalculate formulas with LibreOffice) |
| Multi-table / relational databases | relbench (prediction over multiple tables with temporal splits), bibench (BI project QA), burr (relational DB → ontology mapping) | keys and joins, granularity, inclusion dependencies, business definitions; can be written as an OSI ontology | joins, sql, profile |
| Data lakes (heterogeneous files) | kramabench (numeric QA over files in mixed formats) | how files correspond, unit and time alignment, cleaning rules | generic table tools (sql, profile) |
| Graphs | ngdbench (QA over large property graphs, including versions with injected noise) | node / edge types, attribute regularities, what is noise | ultra (interface only; bring your own checkpoint) |
| Equations and scientific data | llm-srbench (numeric data → symbolic formulas), newtonbench (discover physical laws by experimenting in a simulator) | formulas, where they hold, experimental methods | newton (simulator experiments), fit |
| Financial time series | alphabench (factor evaluation on China A-share data) | judgments on factor signal and stability | generic table tools (sql, profile) |
| Text | text (any document collection, no tasks) | claims and entity relations in the text, extractable into a knowledge graph | autoschemakg (text → knowledge graph) |
| Agent traces | traces (Codex / Claude Code sessions, ATIF and other formats), whoandwhen (multi-agent failure logs); personal sessions via `kb collect` | project conventions, how tools and commands behave, causes of failures and their fixes | all converted to ATIF traces; knowledge cites individual steps |

Scenarios, metrics, dev splits and known limitations of each entry are in
[docs/datasets.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/datasets.md).
`knosis list` lists all entries, `knosis describe <name>` shows the data card, `knosis download <name>` fetches the data
(datasets are not shipped with the package). Tools (`knosis tool list`, `knosis tool card <name>`) only produce knowledge
to be verified; they never modify the data.

## Documentation

The documents below are currently in Chinese.

| Document | Contents |
| --- | --- |
| [docs/knowledge.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/knowledge.md) | knowledge format, status and evidence, rules for consolidation and compaction |
| [docs/interfaces.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/interfaces.md) | how tools, skills and MCP divide the work, and how to connect agents |
| [docs/datasets.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/datasets.md) | data entries, metrics, Python API |
| [docs/demos.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/demos.md) | demos and results on each dataset (web version: [live demo](https://eason-nuosen.github.io/Knosis/)) |
| [docs/scope.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/scope.md) | scope and positioning |
| [docs/extending.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/extending.md) | adding datasets, evaluations or tools |
| [docs/design.md](https://github.com/Eason-nuosen/Knosis/blob/main/docs/design.md) | design background (four layers: data / knowledge / tools / decision) |

## License

Code: Apache-2.0. Datasets and model weights have their own licenses, see `datacards/` and each tool's `TOOL.md`;
Knosis does not distribute data or weights.
