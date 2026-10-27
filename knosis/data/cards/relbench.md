# RelBench — prediction tasks on relational databases (multi-table + temporal splits)

## Source

Stanford STAR / Kumo.AI. **RelBench** (NeurIPS 2024 Datasets & Benchmarks),
arXiv **2407.20060**; **RelBench v2** (ICLR 2026 DATA-FM Workshop), arXiv **2602.12606**.
Website https://star-project.stanford.edu/relbench ;
code https://github.com/stanford-star/relbench ;
data https://huggingface.co/datasets/stanford-star/relbench-v1 (databases added in v2 are in `relbench-v2-extra`).
Public, **not gated**, no application needed.

Get it: `knosis download relbench`

**Licensing is layered; do not look at just one.**
- Code / tools: **MIT** (LICENSE at the repository root).
- HF dataset collection: **CC BY-SA 4.0** (note the share-alike).
- **Each database keeps the license of its own upstream source**: for exact terms read `STATS/databases.parquet` in the repository.

Size: v1 has 7 databases / 30 tasks; v2 expands to 11 databases / 66 tasks.
Table counts vary a lot: rel-f1 has 9 tables, rel-trial has 15, rel-hm only 3.

**If the `relbench` package is installed locally**: v3 fetches data from the HF Hub automatically and caches it in
`~/.cache/huggingface/hub` (overridable with `$HF_HOME`). **`RELBENCH_CACHE_DIR` no longer has any effect**;
it is not read even if set. Knosis does not depend on that package and reads the local directory directly.

## Description

RelBench is a predictive learning benchmark on relational databases: each database is a set of multi-table data + several entity-level prediction tasks,
with a unified (temporal) split and evaluation.

**Data layout** (v3, self-describing folders):

```
<db>/
  manifest.yaml             # tables, primary keys, foreign-key graph, temporal split points: the only authoritative source
  db/<table>.parquet        # one parquet per table, pure data, no relbench metadata at all
  tasks/<task>/
    manifest.yaml           # task definition (including the DuckDB SQL used to regenerate labels)
    {train,val,test}.parquet
```

**Key point: all keys and time columns are in `manifest.yaml`, not in the parquet metadata.**
So reading only the parquet will not give you the foreign-key relationships; you must parse the manifest.

Splits are **temporal**, not random: `val_timestamp` / `test_timestamp` give the two split points.
The default behavior of `get_db()` is to hide rows after `test_timestamp`; this is correct:
**evaluating with the untruncated full database is leakage**.

Good for: multi-table joins, entity-level classification / regression / recommendation, generalization under temporal splits, modeling relational structure.
Not good for: settings that require transfer across databases; also not for directly comparing absolute metrics across databases (task difficulty varies widely).

Pitfalls (all explicitly documented upstream, not guesses):
- **`rel-f1/driver-dnf` has a known, deliberately retained label leak**: its SQL lacks the upper bound
  `date <= t.timestamp`, so drivers who only have races after the split point leak in. Upstream **intentionally does not fix it** to stay comparable with published
  numbers. Knosis does not fix it either: if you fix it, your numbers will not match the leaderboard. Be aware of this.
- **The test tables of recommendation tasks already have the target column hidden** (from v3 on, only the time and source entity columns remain).
  Reading the target column from the test table the v2 way silently returns garbage.
- Temporal label windows may cross split points. rel-f1's val (2005) and test (2010) are far apart,
  but **rel-hm's val→test gap is only 7 days**, while the label window spans multiple days: this is the easiest place to trip.
- Upstream **has changed published labels** (rel-event/user-repeat's training set went from 3842 rows to 2972 rows, etc.).
  `regenerate=True` recomputes labels from the SQL for reconciliation; this is a ready-made self-check.
- `get_db()` / `get_table()` **no longer cache** in v3; calling them in a loop rereads from disk repeatedly.
- Underscores in task names are not normalized: v2 has underscored names like `event_interest-interested` and `beer_ratings-total_score`;
  do not apply string cleaning.
- v3 has only three evaluators left: `roc_auc` (binary classification), `map` (recommendation), NMAE (regression).
  The large batch of f1 / mae / rmse / r2 / mrr has been removed; bring your own if you need them.
- When a bare database name cannot be resolved it **falls back to relbench-v1**, so a misspelled database name gives a puzzling error rather than "unknown database".

Tasks are typed as `forecast` (labels computed by SQL, reproducible) / `autocomplete` (predict an existing column) /
`recommendation` / `external` (TGB, 4DBInfer: data only, no built-in evaluator).
