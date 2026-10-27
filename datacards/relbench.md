# RelBench

| Item | Value |
| --- | --- |
| Paper v1 | RelBench: A Benchmark for Deep Learning on Relational Databases |
| arXiv v1 | **2407.20060** (2024-07-29), NeurIPS 2024 Datasets & Benchmarks |
| Paper v2 | RelBench v2: A Large-Scale Benchmark and Repository for Relational Data |
| arXiv v2 | **2602.12606** (2026-02-13), ICLR 2026 DATA-FM Workshop |
| Position paper | Relational Deep Learning, arXiv **2312.04615**, ICML 2024 |
| Code | https://github.com/stanford-star/relbench (the old URL `snap-stanford/relbench` 301-redirects here) |
| Data | https://huggingface.co/datasets/stanford-star/relbench-v1 · `…/relbench-v2-extra` |
| Website | https://star-project.stanford.edu/relbench |
| Access | Public, not gated, no request needed |
| **License** | Code **MIT**; HF collection **CC BY-SA 4.0**; **each database has its own upstream terms** |
| Package version | `relbench` is currently **3.0.2** (requires-python ≥3.10) |

## License (layered; do not look at just one)

- **Code / tooling: MIT.** The repo-root `LICENSE` says
  `The MIT License (MIT) / Copyright (c) 2023 RelBench Team`.
  Note that PyPI's `info.license` field is `None` and the GitHub API license key is null,
  but the badge and the LICENSE file consistently say MIT.
- **HF dataset collection: `cc-by-sa-4.0`** (stated explicitly in the data card YAML; **not MIT**).
  **CC BY-SA is share-alike**: the clause propagates if you redistribute.
- **⚠️ Each database keeps the license of its upstream source.** README, verbatim:
  *"CC BY-SA 4.0 for the collection. **Each database keeps the license of its source**;
  see `STATS/databases.parquet`."*
  **For exact terms you must read that table.**

## Upstream `relbench` package API (3.x)

**The `relbench` 3.x loader differs completely from older tutorials.** Per `MIGRATION.md`, all of the following are **gone**:

- `relbench.datasets.get_dataset` / `get_dataset_names` / `download_dataset`
- `relbench.tasks.get_task` / `get_task_names` / `register_dataset` / `register_task` / `download_task`
- the `download=` argument

`load_task` / `get_task_names` now live on the **dataset object**:

```python
import relbench
dataset = relbench.load_dataset("rel-f1")        # bare name, or "org/repo[/subdir]", or a local path
db      = dataset.get_db()
task    = dataset.load_task("driver-position")
train   = task.get_table("train")                # train / val / test
metrics = task.evaluate(test_pred)
```

Old tutorials (the `get_dataset("rel-f1")` style) do not run. For the old behavior pin `relbench==2.1.2`
(but its download server is deprecated).

**`RELBENCH_CACHE_DIR` has no effect**: it is silently ignored. The cache is in the standard HF location
(`~/.cache/huggingface/hub`, overridden by `$HF_HOME` or `$HF_HUB_CACHE`).

**No pinned revision**: unless you pass `revision=` explicitly, you get the latest `main`, so **the data can change under you**.

## Obtaining

```bash
knosis download relbench                      # all of relbench-v1
knosis download relbench --include 'rel-f1/*'    # a single database
```

Knosis **does not depend on the `relbench` package**; it reads the HF files directly from `data/relbench/<db>/`.
`root=` points to a different directory containing `<db>/` subdirectories: `load_dataset("relbench", "rel-f1", root=...)`.

Dependencies of the `relbench` package (not needed by Knosis): `pandas`, `huggingface_hub`, `pyyaml`, `pyarrow`, `numpy`, `duckdb`,
`scikit-learn`, `typing-extensions`, `tqdm`.

## Size

- v1: **7 databases / 30 tasks**. Databases: `rel-amazon`, `rel-avito`, `rel-event`,
  `rel-f1`, `rel-hm`, `rel-stack`, `rel-trial`.
- v2 adds 4 databases (SALT, RateBeer, arXiv, MIMIC-IV) + 36 new tasks
  (23 of them Autocomplete) -> **11 databases / 66 tasks** in total.

Tables per database (verified): `rel-f1` 9, `rel-stack` 7, `rel-trial` 15, `rel-hm` 3.

**⚠️ MIMIC-IV's access terms are unverified**, and the public `relbench-v2-extra` file tree
**shows no `rel-mimic` directory**: this entry is unconfirmed; do not treat it as publicly available.

Knosis scenarios are the seven v1 databases.

## Layout

```
<db>/
  manifest.yaml              # tables, primary keys, foreign-key graph, time cutoffs: **the only authoritative source**
  schema.svg
  db/<table>.parquet         # one parquet per table, **pure data, no relbench metadata**
  tasks/<task>/
    manifest.yaml            # task definition (including the DuckDB SQL that regenerates labels)
    {train,val,test}.parquet
  README.md
```

The repo root also has `regression_stds.json`, `STATS/databases.parquet`, `STATS/tasks.parquet`.

**Key point: "db" is a directory name, not an SQLite file.** And **all keys and time columns are in the manifest**,
not in the parquet: reading the parquet alone does not give you foreign-key relations.

Actual `rel-f1/manifest.yaml` content (excerpt):

```yaml
name: rel-f1
manifest_version: 1
val_timestamp: '2005-01-01'
test_timestamp: '2010-01-01'
tables:
  races:
    pkey: raceId
    time_col: date
    fkeys:
      circuitId: circuits
  constructors:
    pkey: constructorId
    time_col: null      # static table
    fkeys: {}
```

## Task names (v1, verified)

`rel-f1` 3 (`driver-dnf` / `driver-position` / `driver-top3`),
`rel-stack` 5, `rel-amazon` 7, `rel-hm` 3, `rel-trial` 5, `rel-avito` 4, `rel-event` 3.

v2-only tasks are in the `relbench-v2-extra` repo (bare names are looked up in both repos in order).
**Note that v2 introduces task names with underscores** (`event_interest-interested`,
`beer_ratings-total_score`, `studies-has_dmc`, `searchinfo-isuserloggedon`):
**underscores and hyphens are not normalized; do not clean the strings.**

## Time splits and label leakage (the most important section)

1. **⚠️ `rel-f1/driver-dnf` has a confirmed leak that is deliberately kept.**
   The published task manifest SQL contains this comment:
   ```
   -- KNOWN ISSUE (…/issues/402): no upper bound `date <= t.timestamp`,
   -- so drivers whose only races are after t.timestamp leak in.
   -- Kept as-is for comparability.
   ```
   This is **real future-information leakage**, **left unfixed on purpose** upstream for comparability with published numbers.
   Knosis uses the published labels as is and **does not fix it** (fixing it would make your numbers incomparable with the leaderboard). But you need to know about it.

2. **Test tables of recommendation tasks hide the target column.** `task.get_table("test")`
   keeps only the time and source-entity columns, with no target list. Code that expects the target there silently gets garbage.

3. **Label windows can cross the cutoff.** The target window of `driver-dnf` is
   `(t.timestamp, t.timestamp + INTERVAL '30 days']`, while the entity filter looks back 1 year.
   rel-f1's val (2005) and test (2010) are far apart, but **rel-hm's val -> test gap is only 7 days**
   (2020-09-07 -> 2020-09-14), while the label window spans several days: the easiest place to slip.

4. **`regenerate=True` is a ready-made reconciliation tool.** It recomputes labels from the manifest SQL.
   The upstream changelog records **three** recomputations of published labels (`rel-event/user-repeat`
   training set 3842 -> 2972 rows; `rel-stack/post-votes` +117/+14; `rel-stack/user-post-comment` +1).
   **Published labels have been wrong before.**

5. **Autocomplete on unsorted tables was misaligned** (fixed, but worth knowing): `rel-amazon/review`,
   `rel-avito/SearchStream`, `rel-event/event_interest` had no primary key and were not sorted by time,
   so labels were "indexed by row position", and row positions differ between the full database and the one truncated at `test_timestamp`.
   `AutoCompleteTask` now rejects unsorted tables without a primary key.
   **Row-position keys + time truncation is a fatal combination.**

6. **`get_db()` / `get_table()` do not cache**: calling them in a loop rereads from disk.

7. **DuckDB version sensitivity**: a fix to the start of autocomplete training sets
   says "every duckdb version includes the first batch of rows", meaning label generation depends on the DuckDB version. **Pin your duckdb.**

8. **The environment variable `RELBENCH_DUCKDB_MEMORY_LIMIT`** is opt-in;
   without it, a runaway task SQL can be OOM-killed by the OS instead of raising a catchable error.

## Evaluators

Upstream `relbench` 3.x has **only three**: `roc_auc` (binary classification), `map` (recommendation), NMAE (regression).
**The long tail of f1 / mae / rmse / r2 / mrr / multilabel_* is not included**: bring your own.
Multiclass / multilabel tasks load, but **have no built-in evaluator**.
Regression NMAE needs a normalizer: use the hosted `regression_stds.json`,
or recompute with `relbench.train_std(task)`.

Task types: `forecast` (SQL-derived labels) / `autocomplete` (predict an existing column) /
`recommendation` (formerly `LINK_PREDICTION`) / `external` (TGB, 4DBInfer;
data only, `evaluate()` without metrics raises).

## How Knosis uses it

- Loader (`knosis/data/loaders/relbench.py`): `load_dataset("relbench", "<db>", task=...)` (default `rel-f1`).
  `schema` is the database `manifest.yaml`; files are `db/*.parquet`; one task per (task, split) with the
  split's parquet as the answer and the task `manifest.yaml` as `meta`.
- Exporter (`knosis/workspace/exporters/relbench.py`), one RelBench task per workspace (default: the first task):
  tables with a time column keep only rows before `test_timestamp` (RelBench's `upto_test_timestamp` convention);
  `data/train.parquet` keeps labels; `val` without labels becomes dev (`data/dev_features.parquet`, `dev` caps the count);
  `test` keeps only the time and entity columns (`data/test_features.parquet`, `limit` samples). Rows are addressed by
  `row_id` (`train-i` / `val-i` / `test-i`). Output: `predictions.csv` with `row_id, prediction`.
- Scorer (`knosis/decision/relbench.py`): binary classification `roc_auc`; regression **`mae`** (not NMAE);
  recommendation `map@k` (`eval_k`, default 10). References: train positive rate (AUROC 0.5),
  train mean / median (MAE), train-most-popular items (MAP@k).
  The knowledge scorer compares joins in ontology units against the manifest foreign keys (precision / recall / F1).
