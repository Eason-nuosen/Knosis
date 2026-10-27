# NewtonBench — $domain

## What the data is

There are no ready-made data files here: you are in a virtual universe whose physical laws have been altered, and you must discover its laws through experiments.
There are $n_tasks questions in total, with question ids of the form `<domain>/<difficulty>/<version>/<experimental system>`; the experimental systems are $systems.
Questions with the same difficulty and version share the same law to be discovered; only the experimental setup differs. Experimental observations may contain noise; how to detect and handle it is up to you.

Parameters of the law:

$params

Run experiments with the `newton` tool (see `TOOLS.md`), from the workspace root:

```bash
knosis tool run newton -- --task <question id> --inputs '<JSON list>' --out stages/<current stage>/newton/<number>
```

`--inputs` is the JSON list inside the `<run_experiment>` tag in the upstream description below; the result is printed and written to `--out`.
Below is the original upstream description of each experimental system (its `<run_experiment>` / `<final_law>` tag formats are replaced here by the tool call and the delivery file, respectively):

$apparatus

## What the downstream task is

For each question, submit the discovered law: Python function source code with the signature `$signature`; you may `import math` or use `np.`.
Deliver JSONL, one line `{"id": question id, "answer": function source string}` each.
Evaluation follows the upstream method: RMSLE against the true law on 5000 randomly sampled points; symbolic equivalence (which needs an LLM judge) is not done.
Dev questions and test questions do not share laws.

## What the knowledge should serve

Knowledge about the forms of laws in this universe, constants, the relationship between experimental systems and laws, and experiment design experience can all be written down for reuse.
