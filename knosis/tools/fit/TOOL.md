---
name: fit
version: "0.1"
kind: program
modality: [table]
stage: [explore, extract, refine]
license: "Apache-2.0（Knosis 自带）"
---

符号表达式拟合：给定含自由常数 `C0, C1, ...` 的表达式，在训练切分上用 `scipy.optimize.curve_fit` 拟合常数，
在留出的验证切分上评估，并给出残差诊断（提示缺了哪一项）。用于方程发现中检验候选公式。

```bash
knosis tool run fit -- --data data/<题名>/train.parquet --target y \
  --expr "C0*x**2 + C1*exp(-C2*t)" --init C2=0.5 --split 0.8 --seed 0 \
  --out stages/2_extract/fit/001 --unit k-7
```

表达式按 Python 语法求值，可用数据列名、`np`，以及 `exp log sin cos tan sqrt abs tanh arcsin arccos arctan pi`（均为 numpy 版本）。
常数初值默认 1.0，`--init C0=1,C2=280` 指定；量级差别大的常数给个初值更容易收敛。
`--split` 为训练比例，按 `--seed` 随机切分。

输出 `fit.json`：拟合常数、训练/验证 NMSE（MSE / Var(y)）、验证最大相对误差与 Acc0.1（所有验证点相对误差 ≤ 0.1，同 LLM-SRBench）、
常数个数，以及验证残差与各输入列及其平方的 Pearson / Spearman 相关（相关高说明缺与该量有关的项）。摘要同时打印到标准输出。
`units.jsonl` 一条 inferred `formula` κ：常数代入后的表达式（6 位有效数字），condition 为训练集上各输入的取值范围，
provenance `tool:fit@0.1(expr=...,data=...)`。
`--unit UNITID`：为该 κ 写 `evidence.jsonl`，验证 NMSE ≤ `--accept`（默认 1e-3）记 support，> `--reject`（默认 0.1）记 refute，否则 undetermined；
用 `knosis knowledge evidence import <out>/evidence.jsonl` 导入。拟合失败（不收敛、非有限值）时 `fit.json` 记录错误、不产出 κ，
evidence 记 undetermined，退出码仍为 0。低 NMSE 只说明在本数据范围内拟合好，不代表定律正确，域外要另行验证。
