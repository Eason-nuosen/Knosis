# KramaBench — $domain

## What the data is

A data lake for the "$domain" domain, under `data/`: $n_files files in total, about $size_mb MB.
File types: $suffixes.
File formats are not uniform and may include tables, geographic data, text, spreadsheet files, etc.; you have to work out which files are relevant to which question.
The data may contain noise; what counts as noise and how to handle it is up to you.

## What the downstream task is

Each question requires end-to-end data processing to answer (finding files, cleaning, merging, computing).
`tasks/dev.jsonl` has $n_dev dev questions; the test questions ($n_test) are given in the decide stage.
Each question's `answer_kind` states the shape of the answer: number, string or list.

Deliver `predictions.jsonl`, one line `{"id": question id, "answer": answer}` each:
write numbers as numbers (no units or thousands separators), strings as the short conclusion itself, and lists as JSON arrays.
Evaluation: numbers must match the ground truth (decimals allow a very small rounding error; some questions are scored by relative error),
strings are compared ignoring case and leading/trailing whitespace, and lists are scored by element-level F1.

## What the knowledge should serve

Make unseen questions on the same data lake answered more accurately: what the files contain, field meanings and units, how files correspond to one another,
data quality and trustworthiness, and commonly used processing methods can all be written as knowledge. Knowledge should be reusable; it should not cache answers to specific test questions.
