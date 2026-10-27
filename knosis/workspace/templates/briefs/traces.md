# Agent traces: $name

## What the data is

$n_traces agent traces, normalized to ATIF traces (`.md` for reading, where `## step <n>` is the step number; `.json` is the structured original).
A step is one user message, or one agent output (text, thinking, tool call); a call's result is attached to the step that issued the call.
In multi-agent traces the speaking agent is marked in the step heading, and sub-agent steps are at the end of the `.md`:

$listing

$env

## Task

Extract **knowledge about the environment** from the traces: what the agent saw in the trace, what it tried, which approaches succeeded or failed, and what the results say about the environment.
What a trace says is that agent's claim, not fact: it may have misread, guessed wrong, or ended up with a wrong answer.
Whatever can be re-verified on the environment data, re-verify before recording evidence; whatever cannot be re-verified stays inferred, with a clear note of which steps it is based on.
Failed attempts are also a source of information (for example, a query result that disagrees with later feedback indicates a problem in the data).

Write knowledge sources as trace steps: `data/traces/<trace id>.json#step/<n>` (for sub-agent steps, `#agent/<sub-agent id>/step/<n>`), joining multiple steps with ` ; `; record evidence separately when re-verifying on the environment.
Write reusable practices from the traces separately according to their nature: conclusions about the environment as ordinary κ, "how to discover / verify a kind of knowledge" as `scope=method`,
and "how to use this knowledge to solve this kind of task" as a skill (`kb/skills/`). Do not store answers to specific questions in the traces as knowledge.

## What the knowledge should serve

Help agents (possibly a different model) doing **other** tasks on the same environment later avoid detours and avoid repeating the same mistakes.
