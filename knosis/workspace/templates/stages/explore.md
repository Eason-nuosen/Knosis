## Goal

Understand the structure, distribution and quality of the data. The data may contain noise (errors, missing values or altered content);
you decide for yourself what is noise and how to detect and handle it. State your basis and uncertainty; no regularities are required at this point.

## Inputs

`BRIEF.md`, `data/`, `TOOLS.md`. Python: `$python`.

$feedback

## Deliverables

`stages/1_explore/notes.md`: what you looked at, what you found, what is uncertain.
Write suspicious items into `kb/knowledge/units.jsonl` with `form=finding`, `status=inferred`; for those with direct support, record a piece of evidence with `knosis knowledge evidence add`.
Put analysis code and tool results in `stages/1_explore/`.

## Acceptance criteria

The notes are non-empty; the knowledge unit structure check passes, and provenance points to specific locations in data files or to feedback records.
Suspicious items are backed by statistics, constraints, contradictions or feedback results. When done, run `knosis ws check .`.
$control