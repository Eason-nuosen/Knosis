---
name: joins
version: "0.1"
kind: program
modality: [tables]
stage: [explore, extract]
license: "Apache-2.0 (bundled with Knosis; the counterpart of BI-Agent's discover_join_relationships, but computed live rather than reading predefined answers)"
---

Multi-table join discovery: finds column pairs where nearly all values of a foreign-key column appear in a unique column of another table (inclusion dependencies),
ranks them by containment and column-name similarity, writes `joins.csv`, and emits one `finding` (inferred) per candidate.
`--ontology DIR` additionally writes a draft of the ontology core layer (`<name>.semantic_model.yaml`, `--name` defaults to `draft`: tables, columns, candidate primary keys, candidate joins),
with provenance `method: tool`; it can be placed directly in `kb/knowledge/ontology/` and then revised by the agent.

```bash
knosis tool run joins -- --tables data/ --out stages/1_explore/joins
knosis tool run joins -- --tables data/ --out stages/2_extract/joins --min-containment 0.95 --ontology stages/2_extract/joins/ontology
```

`--min-containment` defaults to 0.9. By default the two column names must also have a similarity (difflib) ≥ `--min-name-similarity 0.5`; set it to 0 to look at values only.
For reference: compared with the relationships built into the Power BI models of the first 25 BI-Bench cases, the default parameters give precision 0.35 and recall 0.63
(0.10 / 0.69 with containment only); the built-in relationships are incomplete, so the precision is a lower bound.

Only integer and string columns are compared (all converted to strings; `1.0` and `1` are treated as equal); boolean and non-integer float columns are skipped.
The foreign-key side must have at least `--min-distinct` (default 2) distinct values, so constant columns are not taken as foreign keys. High containment does not mean the join is semantically valid; verify it.
