## Goal

Round $round: improve the knowledge layer so that it better supports the downstream task. The data may contain noise; you decide how to judge and handle it.
You may merge duplicates (the merged one becomes merged + merged_into), generalize conditional rules, re-verify, handle contradictions, retract knowledge that does not hold, and mark affected derived knowledge stale.
Feedback results are themselves a source of knowledge: write conclusions drawn from them as κ as usual, and record feedback's support for or refutation of a piece of knowledge as evidence (method=feedback).
Inherited knowledge and ontologies can likewise be corrected; keep the evidence chain when correcting.
After reviewing feedback, summarize "how to use knowledge to solve this kind of question" as a skill (create or modify `kb/skills/`).

## Inputs

The current `kb/` (knowledge/units.jsonl, knowledge/ontology/, skills/) and `evidence/` (ledger.jsonl, feedback/), `data/`, changelogs of previous rounds, `TOOLS.md`.
Python: `$python`.

$feedback

## Deliverables

Update `kb/knowledge/units.jsonl` (and the ontology and skills when needed);
`stages/3_refine/round_$round/changelog.md` records changes, reasons and verification results.
When there are dev questions, answer them with this round's knowledge and write to `stages/3_refine/round_$round/dev_$output`;
the same directory may include `dev_<same name>_used_units.jsonl` (each line `{"id": question, "used_units": [knowledge id or skill:<name>]}`):
when feedback is submitted, Knosis uses it to compute, per question type, the utility of each piece of knowledge and skill (candidates and evidence with scope=usage);
in driven mode, the runner automatically submits it at the end of this round to get one round of feedback, and the results appear in the next round's prompt.
Put code and tool results in the current round directory.

## Acceptance criteria

I1 source and derivation references are complete, I5 retraction propagation passes; status is consistent with evidence; cross-file references in the ontology and κ `about` references resolve;
`feedback:` sources point to existing feedback records. The derived_from of a merged unit points to the original units; do not lose sources, conditions or exceptions.
When done, run `knosis ws check .`; after it passes, K_$round is saved;
decide the number of rounds yourself, and when finishing run `knosis ws goto . decide`.
$control