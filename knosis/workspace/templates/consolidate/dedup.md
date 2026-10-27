# Consolidation 1/3: dedup

Knowledge layer root: `$base` ($n_units active κ, $n_inactive inactive). Goal: merge units that say the same thing into one, so that knowledge retrieved later has no duplicates.

## Candidates

Suspected duplicates found by Knosis via content similarity and shared anchored objects (only hints; not all are necessarily duplicates):

$candidates

You may also search further yourself with `knosis knowledge select --ws $base --text <keywords>`.

## Procedure

1. Judge pair by pair whether they are the same thing: same object, same assertion, compatible conditions. Units that are merely related, have different conditions, or have different scope (one about a specific object, one about an overall regularity) are not duplicates.
2. If duplicate: keep the one that is more accurate, has more complete conditions and more evidence as the primary unit; when needed, rewrite its `content` / `condition` to combine the information of both,
   without losing conditions and exceptions; `provenance` merges the sources of both (joined with ` ; `).
3. Change the other to `"status": "merged"`, add `"merged_into": "<primary unit id>"`, and keep all other fields as they are (it becomes an alias; derived units, skills
   and the outline that reference it are resolved through the alias to the primary unit). The evidence of the merged unit need not be moved.
4. Do not delete any unit; only modify `kb/knowledge/units.jsonl`. When you need to add evidence, use
   `knosis knowledge evidence add --ws $base --unit <primary unit> --verdict support --method derivation --source merge:<merged unit> --note "<basis>"`.

## Acceptance check

`knosis knowledge check --ws $base` introduces no new problems$check_note; no unit was deleted.
Finally, explain in two or three sentences which ones you merged, and which candidates are not duplicates and why.
