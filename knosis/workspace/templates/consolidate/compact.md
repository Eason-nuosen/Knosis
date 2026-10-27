# Consolidation: compaction

Knowledge layer root: `$base` ($n_units active κ, $n_inactive inactive). Goal: $goal

## Range

$scope

You may search further yourself with `knosis knowledge select --ws $base --text <keywords>`, and see the history of a piece of knowledge with `knosis knowledge trace <id> --ws $base`.

## Procedure

Compaction only reduces the count; it loses no information: every compacted unit must be reachable via its alias to the unit that summarizes it.

1. Find groups of units that can be stated together: several scattered assertions about the same object, instances of the same regularity on several objects, similar method steps, the same thing in different wording.
   Do not merge units whose conditions differ, that contradict each other, or whose scope spans so widely that merging would lose information.
2. Keep one unit per group as the primary unit (you may also create a new summarizing unit): rewrite its `content` / `condition` to include the group's conditions, exceptions and key numbers;
   `provenance` merges the sources of the units in the group (joined with ` ; `); the `status` of a new summarizing unit takes the weakest status in the group (even if there is verified, it can only be inferred,
   unless you add evidence for it: `knosis knowledge evidence add --ws $base --unit <primary unit> --verdict support --method derivation --source merge:<merged unit> --note "<basis>"`).
3. Change the other units in the group to `"status": "merged"`, add `"merged_into": "<primary unit id>"`, and keep all other fields as they are (they become aliases; derived units, skills
   and the outline that reference them are resolved through the alias to the primary unit).
4. Units of very low value that are fully covered by another unit are likewise merged into the unit covering them (merged); do not retract them directly.
5. Do not delete any unit; modify `kb/knowledge/units.jsonl` (and necessary evidence). In the outline `kb/outline.yaml`, the knowledge graph `kb/graph.json` and the flows `kb/flows/`,
   repoint references to merged units to the primary unit (if this duplicates a reference in the same place, remove one), and make no other changes.$topic_rule

## Acceptance check

`knosis knowledge check --ws $base` introduces no new problems$check_note; no unit was deleted; the number of active units decreased; every unit that became inactive in this step has `merged_into`
(or `superseded_by`) pointing to an active unit. If there is truly nothing to compact, change nothing.
Finally, explain in two or three sentences which groups you compacted and why each could be merged, and which looked similar but were not merged and why.
