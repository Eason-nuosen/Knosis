# LLM-SRBench — $split

## What the data is

$n_tasks scientific equation discovery questions. Each question has one output variable and several input variables, with a description of what each variable means;
training data is in `data/<question name>/train.parquet`, with the variable names as column names. The question lists (variables, descriptions, data paths) are in
`tasks/dev.jsonl` (dev questions) and `tasks/tasks.jsonl` generated in the decide stage (test questions); the data for both is already in `data/`.
The data may contain noise; how to detect and handle it is up to you.

Example `$example_id`: output `$example_output`, inputs $example_inputs.

$example_desc

## What the downstream task is

For each question, give an expression for the output variable in terms of the input variables. Evaluation is done on held-out test points (LSR-Synth also has out-of-distribution points),
looking at the numeric error (NMSE) and whether the maximum relative error stays within 10% (Acc₀.₁).

Deliver JSONL, one line `{"id": question id, "answer": expression string}` each. The expression is one line of Python/numpy code:
it may only use input variable names, numeric constants and functions under `np.` (e.g. `np.exp(-0.5*t) * P + 2.1*np.sqrt(P)`);
do not write function-call forms like `P(t)`; you must estimate constants as concrete numbers yourself.

## What the knowledge should serve

Knowledge about equation forms in each domain, relationships between variables, constant values and conditions of validity helps you write equations faster and more accurately on questions of the same kind.
Do not cache answers to specific test questions as knowledge in advance.

An equation discovered on a question is written as a κ with `form=formula`, with `{"task": question id, "expression": expression written the same way as in the delivery}` in `meta`,
and `condition` stating the observed variable ranges. Keep rejected candidate equations too (mark them retracted and record the refuting evidence), so the discovery process is traceable.
Equations with `meta.expression` are recomputed on the held-out points to assess whether the knowledge itself holds (scored separately from the delivered answers).
