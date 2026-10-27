# TabArena — $name

## What the data is

Single-table dataset `$name`, target column `$target`, problem type `$problem_type`.
The training set has $n_train rows and the test set has $n_test rows, with $n_features features in total.
`data/train.parquet` contains training labels; `data/test_features.parquet` does not contain the target column.
The `row_id` in both tables is the original row number, not a predictive feature.

Original columns and types:

$columns

Dataset description:

$description

## What the downstream task is

Predict `$target` for every row of the test feature table, keeping the corresponding `row_id`.
For classification you may also provide per-class probabilities (column names `probability_<class>`). Test labels are not in the workspace and must not be searched for or read.
If `data/dev_features.parquet` exists, it contains dev rows with labels removed; you can submit predictions on them for feedback.

## What the knowledge should serve

The data may contain noise; what counts as noise and how to handle it is up to you.
Extract reusable patterns between features and the target, and record their conditions of validity and counterexamples; validate using only the training data and feedback.
Patterns that can be written as SQL checks (table name `train`) go into the κ's `check`; at evaluation these checks are rerun on labeled held-out rows
to assess whether the knowledge itself holds (scored separately from the prediction score).
