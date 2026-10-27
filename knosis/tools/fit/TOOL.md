---
name: fit
version: "0.1"
kind: program
modality: [table]
stage: [explore, extract, refine]
license: "Apache-2.0 (bundled with Knosis)"
---

Symbolic expression fitting: given an expression with free constants `C0, C1, ...`, fit the constants on the training split with `scipy.optimize.curve_fit`,
evaluate on the held-out validation split, and report residual diagnostics (hinting at which term is missing). Used in equation discovery to test candidate formulas.

```bash
knosis tool run fit -- --data data/<task>/train.parquet --target y \
  --expr "C0*x**2 + C1*exp(-C2*t)" --init C2=0.5 --split 0.8 --seed 0 \
  --out stages/2_extract/fit/001 --unit k-7
```

The expression is evaluated with Python syntax and may use data column names, `np`, and `exp log sin cos tan sqrt abs tanh arcsin arccos arctan pi` (all numpy versions).
All columns except the target and `row_id` are inputs.
Constants start at 1.0 by default; set initial values with `--init C0=1,C2=280`. Giving an initial value to constants of very different magnitude helps convergence.
`--split` is the training fraction; the split is random, controlled by `--seed`.

Outputs `fit.json`: fitted constants, training / validation NMSE (MSE / Var(y)), validation maximum relative error and Acc0.1 (every validation point has relative error ≤ 0.1, as in LLM-SRBench),
the number of constants, and the Pearson / Spearman correlations of validation residuals with each input column and its square (a high correlation suggests a missing term involving that quantity). A summary is also printed to stdout.
`units.jsonl` holds one inferred `formula` κ: the expression with constants substituted (6 significant digits), with the training-set range of each input as its condition
and provenance `tool:fit@0.1(expr=...,data=...)`.
`--unit UNITID`: writes `evidence.jsonl` for that κ: validation NMSE ≤ `--accept` (default 1e-3) is recorded as support, > `--reject` (default 0.1) as refute, otherwise undetermined;
import it with `knosis knowledge evidence import <out>/evidence.jsonl`. If the fit fails (no convergence, non-finite values), `fit.json` records the error, no κ is produced,
the evidence is undetermined, and the exit code is still 0. A low NMSE only means a good fit within the range of this data, not that the law is correct; validate out of domain separately.
