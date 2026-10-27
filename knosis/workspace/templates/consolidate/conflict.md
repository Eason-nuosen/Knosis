# Consolidation 2/3: contradiction handling

Knowledge layer root: `$base` ($n_units active κ). Goal: mutually contradictory assertions about the same object must either be resolved or explicitly marked; the knowledge base must not contradict itself.

## Candidates

Related units anchored on the same object, and contested units (only hints):

$candidates

## Procedure

Judge each one whether they are truly mutually exclusive (cannot both hold for the same object under the same condition). A true contradiction has three ways out:

1. **Narrow the condition**: both hold under different conditions (different subsets, time periods, versions, parameter ranges). Rewrite each one's `condition` to state the range clearly, and re-verify when needed.
2. **Adjudicate with new evidence**: $verify After recording the evidence, change the overturned side to `retracted` (its descendants become stale / retracted by retraction propagation).
3. **The environment changed**: the old conclusion once held, but the data, tool or environment version changed. Change the old unit to `stale` and add `"superseded_by": "<new unit id>"`.

For those that cannot be adjudicated for now: both sides add each other in `"conflicts_with": ["<other id>"]`, and at least one side is changed to `contested` (contested is not selected by default; decide later when there is evidence).
Do not delete any unit; only modify `kb/knowledge/units.jsonl`, and record evidence with `knosis knowledge evidence add --ws $base ...`.

## Acceptance check

`knosis knowledge check --ws $base` introduces no new problems$check_note; for every `conflicts_with` pair, if both are still active, at least one is contested.
Finally, explain in two or three sentences which contradictions you handled and which way out each took, and which candidates are not contradictory.
