# RelBench — $db / $task

## What the data is

$description

The relational database is in `data/db/<table>.parquet` and contains only records before $cutoff (the test time); tables without a time column are complete.
The data may contain noise; what counts as noise and how to handle it is up to you.

Tables:

$tables

Schema (primary key / time column / foreign keys):

$schema

## What the downstream task is

Task `$task` ($task_type): $task_description

- `data/train.parquet`: training samples, including the target column `$target` (timestamps before $val_timestamp).
- `data/dev_features.parquet`: $n_dev dev samples (after $val_timestamp), with only $keys and no labels; you can submit them for feedback.
- `data/test_features.parquet`: $n_test test samples (after $cutoff), with only $keys.

Each sample is predicted at the time given in its time column, using only information from before that time.
Deliver a CSV with two columns, `row_id` and `prediction`; $format.

## What the knowledge should serve

Make predictions for entities of the same kind at future times more accurate: knowledge about relationships between tables, entity behavior, temporal patterns and data trustworthiness can all be extracted.
Knowledge should be reusable; it should not cache answers to specific test samples.
