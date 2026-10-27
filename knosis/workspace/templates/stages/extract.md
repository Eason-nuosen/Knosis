## Goal

Extract reusable facts, rules, patterns, equations and schema constraints that serve the downstream task.
State the conditions under which they hold and the exceptions; do not store answers to specific questions as knowledge.

## Inputs

`BRIEF.md`, `data/`, `stages/1_explore/notes.md`, existing findings and `TOOLS.md`.
Python: `$python`.

$feedback

## Deliverables

Update `kb/knowledge/units.jsonl`; you may append, modify or retract existing units.
Structural knowledge (schema, joins, concepts and mappings) can be written as an ontology under `kb/knowledge/ontology/` (three OSI layers), referenced from κ with `about`.
Put analysis and verification code in `stages/2_extract/`.

## Acceptance criteria

The knowledge layer (κ or ontology) is non-empty and the structure check passes; every piece of knowledge records condition.
Rules and equations are verified on the data (or with feedback or tools), with one piece of evidence recorded per verification; those that can be written as executable checks go into `check`, then run `knosis knowledge verify`.
Do not delete refuted candidates; mark them retracted (or narrow the condition and re-verify), so that the discovery process is traceable; derived knowledge records derived_from.
Write the steps you used to discover knowledge, which can be followed on other data, as meta-knowledge with `scope=method` (form is usually procedure).
When done, run `knosis ws check .`; after it passes, the K_0 snapshot is saved.
$control