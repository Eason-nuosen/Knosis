# BI-Bench

## What the data is

Multi-table data from real Power BI projects, $n_cases cases in total; each case is a directory containing that project's CSV tables.
Table and column names are kept as in the original project (they may contain typos); many columns mix numbers and text, so reading them as strings is safer.
The data may contain noise; what counts as noise and how to handle it is up to you.

$cases

$metadata

## What the downstream task is

Each case has one business question extracted from a user dashboard, and every answer can be computed from that case's tables:
you have to decide which tables to use, how to join them, and whether a transformation such as unpivot is needed first, then aggregate.
`tasks/dev.jsonl` has $n_dev dev questions (you can submit them for feedback); there are $n_test test questions, given only in the decide stage.

Deliver JSONL, one line `{"id": case id, "answer": answer}` each; the answer is a table `{"columns": [...], "rows": [[...], ...]}`
or a single value. Evaluation follows the upstream BI-Bench convention: matching any reference answer counts as correct; when the reference answer is a single value, it only needs to appear in your table;
otherwise the shapes must agree and cells are matched as multisets (numeric rtol=1e-2, atol=0.5, row and column order ignored).

## What the knowledge should serve

Make unseen business questions of the same kind answered more accurately: the meaning and granularity of tables, relationships between tables, required transformations, and common definitions and pitfalls can all be extracted.
Knowledge should be reusable; it should not cache answers to specific test questions.
