# Agent traces (Codex / Claude Code / generic agents → a source of verifiable knowledge)

## Source

No fixed origin; the user points to their own trace files: `knosis ws init traces <name> -o paths=<files or globs, comma-separated> [-o env=<the data directory at the time of the traces>]`.
Knosis only reads the original files, never writes them.

## Description

Supported formats (auto-detected, see `knosis.data.traces`):

- Codex: `~/.codex/sessions/**/rollout-*.jsonl` (tested with CLI 0.147 / 0.149 / 0.160 / 0.163)
- Claude Code: session JSONL (`~/.claude/projects/<project>/<session>.jsonl`, tested with 2.1.x), with `subagents/agent-*.jsonl` in the same-named directory as sub-agents
- Step-by-step records: `{instruction, steps: [{reasoning, response, code, env_feedback}], success}`, such as agent-rsi's AppWorld ReAct traces
- OpenAI-style messages (a JSON list, JSONL, or `{"messages": [...]}`)
- One Who&When log (GT fields do not go into the trace); traces already in ATIF v1.7

Normalized to **ATIF v1.7** (Harbor's Agent Trajectory Interchange Format) and written to the workspace as `data/traces/<id>.json` (plus a `.md` for reading):
a step is one user / system message, or one agent output (text, thinking, tool call); a call's result is attached to the step that issued the call.
Knosis's supplementary information is in `extra.knosis`: source format and version (`tested` false means that version has not been tested), counts of records mapped or skipped per source record type,
truncation (a single text segment over 4000 characters), pairings inferred by position (`paired_by`), and the speaking agent in multi-agent traces.
Knowledge cites traces as `data/traces/<id>.json#step/<n>`, and sub-agent steps as `#agent/<sub-agent id>/step/<n>`.
Step sequences in the older format (`<id>.jsonl`) are converted with `knosis migrate`, which also rewrites the cited step numbers.

**Key conventions**

- What a trace says is that agent's claim, not fact. Knowledge that cites only traces stays inferred;
  when `env` is given, it can be re-verified on `data/env/`, and evidence is recorded after re-verification (`method` is data / check / tool).
- Do not store answers to specific questions in the traces as knowledge; reusable practices are split into method (how to discover / verify) and skill (how to use knowledge to solve tasks).

## Evaluation

There is no task metric; the scorer reports the fraction of knowledge that cites steps that actually exist (`cites_trace`), and the fraction supported by non-trace evidence (`env_verified`).
Transfer gains are measured separately: merge the extracted knowledge into the knowledge base, then compare none / K_inherit on new questions in the same environment.
