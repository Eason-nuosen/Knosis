# Collect knowledge from recent agent sessions

Knowledge base: `$kb` (the current directory, a git repository; currently $n_units κ; knowledge base outline: $outline).
The trajectories of the following $n sessions have been unified into ATIF trajectories under `evidence/traces/` (`.md` is for reading, `## step <n>` is the step number; `.json` is the structured original,
one step is one model output or one user message, and the result of a call is attached to the step that issued the call):

$listing

## Task

From these sessions, extract **knowledge that future agents can use and that can be refuted by environment evidence**, and write it into this knowledge base:

- Conclusions about the environment: structure and conventions of projects / repositories, characteristics and pitfalls of data, actual behavior of tools and commands, server and environment configuration, causes of errors and how to fix them;
- `scope=method` (meta-knowledge): steps for discovering or verifying a class of knowledge;
- skill (`kb/skills/<name>/SKILL.md`, format as in existing skills or the `knosis` instructions): how to use this knowledge to solve a kind of task; write one only when there is a clear reusable procedure.

Do not record: user preferences and conversation memory (this is not knowledge and cannot be refuted by the environment), one-off answers to specific tasks, small talk, keys and passwords.
What the agent says in a session is its claim, not fact; where command output in the trajectory directly supports it, record a piece of evidence, otherwise keep it `inferred`.
If nothing in the sessions is worth recording, you may add nothing at all.

## How to write

1. First look at existing knowledge to avoid duplicates: `knosis knowledge outline --ws .`, `knosis knowledge select --ws . --text <keywords>`.
   - Says the same thing as an existing unit: do not add a new one; record a supporting piece of evidence for it;
   - Contradicts an existing unit: record a refuting piece of evidence, change it to `contested` (or `retracted` when certain), write the new knowledge as usual and explain in `condition`.
2. Write new units into `kb/knowledge/units.jsonl` (one JSON per line): `id` (like `collect/<topic>-<short description>`, unique across the knowledge base), `content`,
   `form` (finding / fact / rule / formula / schema / tool / procedure), `status` (observed / inferred / verified),
   `scope` (object knowledge instance / relation / dataset, meta-knowledge method / usage), `provenance`, `condition` (applicable range: which project, directory, tool version, etc.).
   Point `provenance` to trajectory steps: `evidence/traces/<session id>.json#step/<n>`; join multiple locations with ` ; `.
3. Evidence: `knosis knowledge evidence add --ws . --unit <id> --verdict support|refute --method data --source evidence/traces/<session id>.json#step/<n> --note "<basis>"`.
   `verified` requires at least one supporting piece of evidence.
4. Only modify `kb/knowledge/units.jsonl`, `evidence/ledger.jsonl` (written with commands), `kb/skills/`; do not modify `evidence/traces/`, `collected.jsonl`, `kb/outline.yaml` (the consolidation step later does dedup, contradiction handling and outline organization uniformly).

## Acceptance check

`knosis knowledge check --ws .` introduces no new problems; the `provenance` of every new unit references a session in this run's `evidence/traces/`.
Finally, explain in two or three sentences what you recorded and what you skipped.
