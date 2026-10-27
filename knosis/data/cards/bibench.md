# BI-Bench — end-to-end business QA on real BI projects

## Source

Hu, He, Zhou, Tok, Kang, Chaudhuri, **BI-Agent and BI-Bench: Towards Automating End-to-End Business Intelligence**,
arXiv **2609.20886** (2026). Repository https://github.com/Hu-Chuxuan/bi-agent (data in `bi-bench/`).

Get it: `knosis download bibench` (`git clone` followed by `git lfs pull`; the tables and GT are all LFS files, about 4 GB once expanded;
requires git-lfs: `conda install -c conda-forge git-lfs`).

**License: not declared.** The repository has no LICENSE file, and the README has no license statement. Treat it as "all rights reserved" and do not redistribute.

## Description

What BI-Bench tests: **given the raw tables of a real BI project, answer one business question from its dashboard.**
100 cases, each from a real Power BI project: several CSV tables (2–52 per case, median 8, 1056 in total)
plus one natural-language question extracted from a user dashboard (e.g. "What are the sum of unit price and the sum of quantity for each order year?").

The difficulty is end-to-end: you have to decide which tables to use, how to join them, and whether a transformation such as unpivot is needed first, then aggregate.

**One scenario per case**: `load_dataset("bibench", "<case id>")`; case ids are the keys of `queries.json`,
and some ids contain hyphens (e.g. `111676720-1`). Without a scenario only the 100 questions are loaded, and no table files are registered.

**Data shape:**

- `ds.files`: the case's tables (keys are file names without `.csv`), plus the original BI project's model metadata:
  `_tables` / `_columns` (table and column definitions), `_relationships` (relationships between tables defined in the project),
  `_joins` (candidate joins mined by the BI-Agent tools, with confidence `weight`). Tables and columns in the metadata reference each other by numeric IDs.
- `ds.tasks`: one question per case; `input` is the business question, and `answer` is a list of GT file paths.

**Evaluation convention (upstream):** a prediction (a table or a scalar) is correct if it matches **any** GT table.
Multiple GTs are usually different formats of the same answer (e.g. `8.95%` and `8.95`).
When the GT is 1×1, the prediction is correct as long as this value appears in it; otherwise the shapes must agree and cells are matched as multisets
(numeric `rtol=1e-2, atol=0.5`, row and column order ignored).

Good for: multi-table understanding and join inference, table-structure knowledge (which tables, which keys, which transformations), end-to-end data analysis agents.
Not good for: questions that need external knowledge to answer (all answers are in the tables).

Pitfalls:
- **`task.meta["oracle"]` is a solution hint** (which tables to use, which transformations are needed), from upstream's `query_metadata.json`;
  do not show it to the agent being evaluated. The upstream BI-Agent tool suite (retrieval / transformation) uses this information.
- Upstream's `tools/data_management_tools/transformation/` contains pre-transformed tables, which are also hints.
- Table names may contain typos (e.g. `Coutnries.csv`); this is how the original project is, do not fix them.
- Reading tables as strings is safer (upstream uses `dtype=str`); many columns mix numbers and text.
