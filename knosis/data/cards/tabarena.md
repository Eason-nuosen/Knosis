# TabArena — a living benchmark for single-table prediction (51 curated datasets)

## Source

Erickson et al., **TabArena: A Living Benchmark for Machine Learning on Tabular Data**,
NeurIPS 2025 Datasets & Benchmarks, arXiv **2506.16791**.
Code https://github.com/autogluon/tabarena ; dataset curation https://github.com/TabArena/tabarena_dataset_curation ;
the data is OpenML task suite **457** (alias `tabarena-v0.1`) https://www.openml.org/search?type=study&study_type=task&id=457 .

Get it: `knosis download tabarena` (requires the `openml` package; exports each task to `data.parquet` + `splits.parquet` + `meta.json`
under `data/tabarena/<dataset name>/`). To fetch only some datasets: `--include <dataset name>`, repeatable.

**License:** all 51 datasets are under public-domain licenses; this is one of the inclusion criteria of TabArena's curation.

The OpenML server is often very slow (measured at about 3 minutes per dataset with per-item requests). The TabArena maintainers provide a backup of the OpenML cache (305 MB):
https://data.lennart-purucker.com/tabarena/openml_dataset_backup/ . Merge the `.openml-cache/` in the zip into
`data/tabarena/.openml/` and then run `knosis download tabarena`; the 51 datasets export in about 20 seconds.

## Description

TabArena is the main leaderboard where tabular foundation models such as TabPFN-2.5, TabICL, Mitra and LimiX are compared side by side with tree models and AutoML.
The 51 datasets were selected from 1053 candidates by the criteria "real, i.i.d., representative, clean license",
covering binary classification, multiclass classification and regression, ranging from a few hundred rows to about 100 thousand rows and up to about 2000 features.

**One scenario per dataset**: `load_dataset("tabarena", "<dataset name>")`. `list_scenarios("tabarena")` lists those exported locally.

**Data shape:**
- `ds.read("data")`: the whole table (DataFrame), **including the target column**, whose name is in `ds.schema["target"]`.
- `ds.schema`: `target` / `problem_type` (binary / multiclass / regression) / `categorical` (categorical feature columns) /
  `n_rows` / `n_features` / `description` (the dataset description on OpenML).
- `ds.tasks`: one task per official repeat × fold split; `meta["train"]` / `meta["test"]` are row numbers,
  and `answer` is the target values of the test rows. **Do not read `answer` outside evaluation, and do not take the target column of test rows from the whole table.**

**Official conventions:**
- Metrics: ROC-AUC for binary classification, log loss for multiclass, RMSE for regression; aggregated across datasets with Elo.
- You must use the official splits and not re-split yourself. Each OpenML task has 10 repeats × 3 folds (30 tasks in total);
  the official TabArena evaluation uses only some of the repeats depending on dataset size; the TabArena code is authoritative for this.
- **TabArena-Lite** is a cheap version that uses only the first split of each dataset (repeat 0 / fold 0), used in the TabPFN-2.5 report.

Good for: single-table classification and regression, evaluating tabular foundation models (the TabPFN kind), comparisons before and after injecting explicit knowledge into non-language foundation models.
Not good for: multi-table / temporal / relational structure (use RelBench for those).

Pitfalls:
- `data.parquet` is the whole table. When taking features of test rows, drop the target column before feeding the model.
- Categorical features are stored as pandas `category` type; some models need you to encode them yourself.
- Different papers report different "TabArena subsets" (TabPFNv2 subset, TabICL subset, Lite); align the subset before comparing numbers.
- The leaderboard is continuously updated (living benchmark); state the version `tabarena-v0.1` when citing.
