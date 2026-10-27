## Goal

Complete the downstream task using the current knowledge layer; adopt only knowledge that is still valid, and do not use stale or retracted units.
Correct knowledge is not necessarily useful for these questions: first use `knosis knowledge select` to pick out relevant knowledge and `knosis knowledge skills` to see whether there is an applicable solving method,
then decide which to use; skills used are written as `skill:<name>` in `used_units`.

## Inputs

`tasks/tasks.jsonl`, `kb/knowledge/units.jsonl`, `kb/knowledge/ontology/`, `kb/skills/`, `data/`.
Python: `$python`.

## Deliverables

`stages/4_decide/$output`.
For graph QA, each JSONL line contains id and answer, with the answer shape described in BRIEF;
for tables, the CSV contains row_id and prediction, and classification may include per-class probabilities.
`stages/4_decide/used_units.jsonl` (recommended): each line `{"id": question or row_id, "used_units": [knowledge id, ...]}`,
used to evaluate whether knowledge actually took part in the decision.

## Acceptance criteria

Each question or test row has exactly one output, with no unknown or duplicate ids; do not search for test answers.
When done, run `knosis ws check .`.
$control