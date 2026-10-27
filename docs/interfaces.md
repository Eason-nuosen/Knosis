# Tools, skills, MCP

What Knosis gives an agent comes in three non-overlapping layers:

| Layer | Where | What | Written by | Evaluated by |
| --- | --- | --- | --- | --- |
| Tools | `knosis/tools/<name>/{TOOL.md, run.py}` | Programs or models run as separate processes: read data, emit inferred / observed κ annotations, never modify data or the knowledge layer | Knosis developers | Reference accuracy in the tool description (e.g. P/R of joins on BI-Bench) |
| Skills | `kb/skills/<name>/SKILL.md` | Part of the knowledge layer: how to apply knowledge to a class of tasks (playbooks), citing κ | The agent (added during RSI based on feedback) | Whether they help (feedback / ablation evidence), not whether they are true |
| MCP | `knosis/mcp.py`, `knosis mcp --ws <dir>` | Protocol adapter: exposes knowledge-layer operations and tool calls as MCP tools, implements no functionality itself | Knosis developers | None; only guarantees checks before writes |

Rule of thumb: something that reads data and produces new annotations is a **tool**; something that describes "do this first, then that, using this knowledge" is a **skill**;
what lets an agent query and write the knowledge layer and call tools without a shell is **MCP**. Research models (TabPFN, ULTRA,
AutoSchemaKG and the like) are always packaged as tools; MCP only launches them via `tool_run` and does not reimplement them.

Separately, `knosis/workspace/templates/SKILL.md` is Knosis's own agent skill (installed into Codex / Claude Code by `knosis install`).
It explains how to use Knosis and is not a skill in the knowledge layer.

## MCP server

```bash
knosis mcp --ws ws/newton        # a workspace; a knowledge base directory also works (no data/, so knowledge_verify and workspace_next are unavailable)
```

| Tool | Purpose |
| --- | --- |
| `knowledge_select` / `knowledge_skills` / `knowledge_index` | Select knowledge (with evidence counts), list skills, object-keyed view |
| `knowledge_trace` | Derivation chain and evidence of one unit |
| `knowledge_outline` | Knowledge outline (a draft if there is none), see below |
| `knowledge_graph` | Knowledge graph summary, the subgraph around an entity, flowcharts, or rule / formula cards |
| `knowledge_add` / `knowledge_update` | Add / modify a κ; checked with `check_units` before writing, rejected with the issues if it introduces new ones |
| `evidence_add` / `knowledge_verify` | Record evidence (returns the issues the unit now needs addressed, e.g. a status change after refutation) / rerun executable checks |
| `knowledge_candidates` | Consolidation candidates: likely duplicates, possible conflicts, contested units |
| `knowledge_check` | Check the whole knowledge layer (including dedup aliases, conflict marks, outline) |
| `tool_list` / `tool_card` / `tool_run` | List tools, read a tool's description, run a tool from the workspace root |
| `workspace_next` | Goal and acceptance criteria of the current stage |

`eval` is not exposed. The server is a hand-written stdio JSON-RPC implementation (no dependency on the `mcp` package), one message per line, supporting
`initialize`, `ping`, `tools/list` and `tools/call`.

With Codex (MCP calls under non-interactive `exec` need approval by default, so allow this server):

```bash
codex exec -C ws/newton \
  -c 'mcp_servers.knosis.command="knosis"' -c 'mcp_servers.knosis.args=["mcp","--ws","ws/newton"]' \
  -c 'mcp_servers.knosis.default_tools_approval_mode="approve"' "<task>"
```

With Claude Code:

```bash
claude -p "<task>" --mcp-config '{"mcpServers":{"knosis":{"command":"knosis","args":["mcp","--ws","ws/newton"]}}}' --allowedTools 'mcp__knosis'
```

## Consolidation and the outline

`knosis knowledge consolidate` runs dedup, conflict resolution, organize and structure in turn (rules in [knowledge.md](knowledge.md), "Consolidation").
The organize step links single-hop knowledge into `kb/outline.yaml`: scenarios (tasks, with the usage meta-knowledge and skills that help them) -> relations between data -> the data itself
(overall patterns, specific objects); method units get their own section or sit under a scenario.

```yaml
title: NewtonBench gravitation family
summary: ...
sections:
  - id: scene                 # unique across the outline
    title: "Scenario: discovering power laws from experimental data"
    summary: one or two sentences on what this section covers and which tasks it helps
    units: [extract/single-axis-scaling, skill:discover-positive-power]   # κ, ontology units or skill:<name>
    notes: optional, for humans (string or list of strings)
    sections: [...]           # subsections
  - id: archive
    title: Retracted or stale
    archive: true             # only archive sections may hold retracted / stale units
```

The outline is a navigation layer: each section summary only restates what its member units already say and adds no assertions, so it needs no evidence.
Induced higher-level patterns are written as separate κ (`provenance: derived`, at least two `derived_from`) and verified as usual.
When an outline exists, `check_knowledge` checks it: referenced units exist, section ids are unique, inactive units appear only in sections with `archive: true`.

```bash
knosis knowledge outline --ws ws/x --draft          # draft generated from scope and anchored files
knosis knowledge outline --ws ws/x --write          # write the draft to kb/outline.yaml (refused if one exists)
knosis knowledge outline --ws ws/x                  # render the current outline (unplaced active units listed at the end)
knosis knowledge candidates --ws ws/x               # likely duplicates, possible conflicts, contested units
knosis knowledge consolidate --ws ws/x              # dedup -> conflict -> organize -> structure; a failing step is retried once, then rolled back
knosis knowledge compact --ws ws/x [--topic TOPIC]  # compaction: merge units that can be stated together, reducing active units
knosis knowledge organize --ws ws/x --prompt-only   # organize step only, print the prompt so the current session's agent does it
```

`consolidate`, `organize` and `compact` accept `--agent codex|claude`, `--model`, `--effort` and `--prompt-only`.
The outlines of a knowledge base and a workspace are independent: `kb merge` does not merge outlines (the consolidation log is appended), so run `consolidate` on the knowledge base after merging.

## Daily loop (personal knowledge base)

`knosis kb collect` (`knosis/knowledge/collect.py`) hands recent Codex / Claude Code sessions to an agent to extract knowledge and writes it back to a standalone knowledge base:
find sessions (by modification time, skipping ones already collected, run inside the knowledge base, run inside a Knosis workspace, or with too few tool calls) -> write traces to `<kb>/evidence/traces/` ->
the agent extracts knowledge following `templates/collect.md` (checking existing knowledge first: duplicates get supporting evidence, contradictions get refuting evidence and become contested) ->
acceptance (no new knowledge-layer issues, new units cite this run's traces; on failure retry once, then restore the knowledge base) -> record in `collected.jsonl` ->
`consolidate` (dedup -> conflict -> organize -> structure) -> commit a git version.

```bash
knosis kb collect --kb ~/kb [--since 1d] [--source codex|claude] [--limit 10] [--min-calls 3] [--include-workspaces] [--no-consolidate] [--dry-run]
```

`knosis install --kb <dir>` writes a marked MCP block into Codex's `config.toml` (idempotent, replaces only its own block, approvals allowed)
and prints the `claude mcp add` command for Claude Code. The MCP `initialize` instructions and the installed skill both tell the agent to read the outline once before a non-trivial task,
search by keywords, and treat inferred / contested knowledge as hints. When `knowledge_select`'s `text` contains spaces it searches by keywords (matching any word, ranked by number of matches).
