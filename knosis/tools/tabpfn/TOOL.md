---
name: tabpfn
version: "0.2"
kind: model
modality: [table]
stage: [explore, extract, decide]
env: knosis-tabpfn
requires: [tabpfn, torch]
license: "Current upstream TabPFN code is Apache-2.0; the model weights use a separate license that changes between versions, and some are gated or non-commercial. Check the license of the checkpoint you choose."
---

Tabular prediction, out-of-fold (OOF) checks for suspicious training labels, and cross-validation of feature variants (to test feature-engineering hypotheses). Inputs are parquet files and are read only;
`row_id` is never used as a feature. Supports class probabilities / entropy for classification, and predictions / quantile intervals / residuals for regression.

```bash
knosis tool run tabpfn -- predict --train data/train.parquet --test data/test_features.parquet --target TARGET --out stages/4_decide/tabpfn --prepare-only
knosis tool run tabpfn -- predict --train data/train.parquet --test data/test_features.parquet --target TARGET --problem-type regression --out stages/4_decide/tabpfn
knosis tool run tabpfn -- oof --train data/train.parquet --target TARGET --folds 5 --out stages/1_explore/tabpfn
knosis tool run tabpfn -- cv --train data/train.parquet --target TARGET --folds 5 --seed 0 \
  --variant 'ratio=add:a_per_b=a/(b+1)' --variant 'no_c=drop:c' \
  --variant 'group_x=subset:kind=="x"' --unit ratio=k-12 --out stages/2_extract/tabpfn_cv
```

`--prepare-only` does not import TabPFN or download a model: it writes `input_summary.parquet`,
an empty `units.jsonl` and `run.json`, for checking the interface on a machine without the model environment. It never outputs fake predictions.
A real `predict` writes `predictions.parquet` (classification: prediction, per-class probabilities, entropy as uncertainty; regression: prediction, 0.1 / 0.9 quantiles, interval width as uncertainty)
and one finding per high-uncertainty test row; `oof` writes `oof_predictions.parquet` (with truth, true-label probability or residual, and a suspicion score)
and one suspicious-label finding per high-suspicion training row. Both keep the top `--topk` rows (default 50). All annotations are inferred and are not written directly to the knowledge layer.

`--problem-type auto|classification|regression`; auto decides from the target dtype (numeric means regression),
so numeric class labels should explicitly use classification.
`--model` is the local checkpoint path for the chosen version; it defaults to the environment variable `KNOSIS_TABPFN_MODEL`, and if that is unset, `auto` uses the installed version's default weights.
`--device` defaults to auto. `--max-rows` defaults to 10000 and `--max-features` to 500;
rows and features beyond these are randomly subsampled with the fixed `--seed`, and the actual training rows and features are recorded in run.json. These are not universal limits across versions;
adjust them to the limits of the chosen weights and your GPU memory. OOF always covers all training rows; only each fold's fit data is subsampled.
OOF does not read test labels; a low true-label probability or a large residual is not sufficient evidence of noise.

`cv`: `--variant NAME=SPEC` is repeatable; `base` is the baseline (all features by default, can be overridden). SPEC is empty or a `;`-separated list of operations:
`drop:a,b` removes columns; `add:name=<pandas eval expression>` adds a column (booleans become 0/1); `subset:<pandas query>` fits and evaluates only on rows that satisfy the condition.
All variants share the same K folds (KFold for regression, StratifiedKFold for classification, `--seed`); subset variants are compared with the baseline on the same rows (the baseline is still fitted on all rows).
Non-numeric columns are encoded as category codes. Metrics: RMSE for regression, log loss for classification (accuracy also reported); lower is better.
Outputs `cv.csv` (per variant: rows, features, mean, std across folds, baseline mean, Δ = variant − baseline, std of the paired per-fold Δ),
and one inferred finding per non-baseline variant (provenance `tool:tabpfn@0.2(cv,variant=...)`).
`--unit VARIANT=UNITID` is repeatable: writes `evidence.jsonl` for that κ: an improvement of more than one paired std is support, a worsening of more than one is refute, otherwise undetermined;
import it with `knosis knowledge evidence import <out>/evidence.jsonl`. With `--prepare-only`, `cv` only writes `cv_plan.csv` (rows and features of each variant).

Install `tabpfn` and Knosis in a dedicated environment (typically on a GPU server); the first real inference may download weights.
Point to that environment with `KNOSIS_TABPFN_PYTHON=/opt/conda/envs/knosis-tabpfn/bin/python`.
Upstream: [PriorLabs/TabPFN](https://github.com/PriorLabs/TabPFN).
Check the code LICENSE and the model license of the HuggingFace checkpoint separately; the code license does not cover the weights.
Knosis does not pin, download or verify any particular weights, and makes no claim that any version is usable commercially.
