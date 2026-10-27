# LLM-SRBench

| Item | Value |
| --- | --- |
| Paper | LLM-SRBench: A New Benchmark for Scientific Equation Discovery with Large Language Models |
| arXiv | **2504.10415** (v1 2025-04-14; v2 2025-06-07) |
| Venue | **ICML 2025 Oral** |
| Authors | Parshin Shojaee, Ngoc-Hieu Nguyen, Kazem Meidani, Amir Barati Farimani, Khoa D Doan, Chandan K Reddy |
| Institutions | Virginia Tech / VinUniversity / CMU |
| Code | https://github.com/deep-symbolic-mathematics/llm-srbench |
| Data | https://huggingface.co/datasets/nnheui/llm-srbench |
| Access | **gated** (`gated: "auto"`, needs HF_TOKEN) |
| **License** | Code **MIT** / paper **CC BY 4.0** / **HF data artifacts not declared** (see below) |
| Upstream version | No explicit version number; fetched as an HF snapshot (`resolve/main/…`) |

## License

The three sources disagree; **treat them separately**:

- **Code: MIT.**
- **Paper: CC BY 4.0.**
- **⚠️ The HF data artifacts themselves have no license field: not declared.** Contact the authors if this matters.

In other words: cloning the code and citing the paper are fine; **redistributing the parquet / HDF5 from HF**
falls under the undeclared part.

## Obtaining

```bash
knosis download llm-srbench     # HF snapshot_download of nnheui/llm-srbench
```

**⚠️ The data is gated (`gated: "auto"`).** Anonymous access to `resolve/main/...` returns **401**,
so CI must have `HF_TOKEN`, and **the terms must first be accepted on the HF website**. This is the step people get stuck on most.

Order: accept the terms on HF, then `hf auth login` (or set `HF_TOKEN`), then `knosis download llm-srbench`.

Load by split:

```python
from knosis.data import load_dataset

load_dataset("llm-srbench", "lsr_transform")            # default split
load_dataset("llm-srbench", "lsr_synth_chem_react")
load_dataset("llm-srbench", "lsr_synth_bio_pop_growth")
load_dataset("llm-srbench", "lsr_synth_phys_osc")
load_dataset("llm-srbench", "lsr_synth_matsci")
```

`list_scenarios("llm-srbench")` returns these five split keys.

The loader finds files under `data/llm-srbench/` recursively: the parquet via `rglob("<split>*.parquet")`
and the HDF5 via `rglob("lsr_bench_data.hdf5")`, so the HF snapshot layout works as is.

## Size

**Small metadata plus one large file**: the 5 parquet files total about **36 KB**, plus one **239 MB** HDF5.

| split key | Paper name | On disk | Domain | Notes |
| --- | --- | --- | --- | --- |
| `lsr_transform` | **LSR-Transform** | 111 | Physics | Symbolic transforms of 100 Feynman equations; memorization-resistant |
| `lsr_synth_chem_react` | LSR-Synth | 36 | Chemistry | Chemistry generative problems |
| `lsr_synth_bio_pop_growth` | LSR-Synth | 24 | Biology | Population growth |
| `lsr_synth_phys_osc` | LSR-Synth | **44** | Physics | Oscillation (⚠️ the paper says **43**, disk has **44**) |
| `lsr_synth_matsci` | LSR-Synth | 25 | Materials | Materials science |

**⚠️ The paper says 239 problems; the disk has 240** (the physics split has 44, not 43).
The cause of the extra problem is unknown; if you need an exact count, diff the `phys_osc` names yourself.

**Two construction routes with different properties:**

- **LSR-Transform** (111 problems): take **100 classic Feynman equations**, **turn one input variable into the target**,
  and solve symbolically with **SymPy** to get a new equation. Only analytically solvable transforms are kept, data points are projected
  into the new equation's valid domain, and complexity is kept within the node-count distribution of the original Feynman set. **This is physics.**
- **LSR-Synth** (129 problems): **GPT-4o** first generates **known terms** and **synthetic novel terms** for a scientific problem,
  then **`solve_ivp`** checks solvability, **GPT-4o** checks novelty, data points are generated,
  and finally **two domain experts manually validate** the expressions and data-point plots.
  Four domains: chemistry 36, biology 24, physics 44, materials 25.

**Memorization resistance is the benchmark's core contribution**: problems are constructed rather than copied from textbooks,
so an LLM cannot pass off a memorized answer as a "discovery".

**Variable metadata**: names and meanings (`symbols` + `symbol_descs`), **but no units**.
No units field, no dimensions, no SI annotation anywhere in the schema.
`symbol_properties` is a free-form list of strings (encoding variable roles/flags);
**upstream has not published its vocabulary**, so do not assume a fixed enum.

**There is also no `domain` field and no `complexity` field**: the domain is determined by which split you load;
complexity must be computed yourself (e.g. sympy `count_ops` on `expression`).

## Layout

```
data/llm-srbench/
├── lsr_bench_data.hdf5                # 239 MB: all numeric data is here
└── data/                              # metadata directory
    ├── lsr_transform-<…>.parquet      # 111 rows
    ├── lsr_synth_chem_react-<…>.parquet    # 36 rows
    ├── lsr_synth_bio_pop_growth-<…>.parquet # 24 rows
    ├── lsr_synth_phys_osc-<…>.parquet       # 44 rows
    └── lsr_synth_matsci-<…>.parquet         # 25 rows
```

**Parquet columns** (all five files share them):

```
name / symbols / symbol_descs / symbol_properties / expression
```

**There is no numeric data in them.**

**Numbers are in the HDF5** (`lsr_bench_data.hdf5`). Group paths:

| split | HDF5 group path |
| --- | --- |
| `lsr_transform` | `/lsr_transform/{name}` |
| `lsr_synth_*` | `/lsr_synth/{dataset}/{name}`, e.g. `/lsr_synth/bio_pop_growth/BPG0` |

Dataset keys inside each group:

```
train / test / ood_test        # ood_test exists only for LSR-Synth; verified against the local HDF5
```

Column 0 of each array is the target (`symbols[0]`), the rest are the inputs in `symbols` order.

Task ids look like `{split}/{name}`; `input` is the `symbol: description` lines, `answer` is `expression`,
`kind` is `symbolic_regression`, and the group path is in `task.meta["hdf5_group"]`.

## Scoring

Upstream has two tracks:

- **Symbolic accuracy**: **GPT-4o as judge** decides mathematical equivalence, **after stripping parameters and constants**.
  **94.6% agreement with two human annotators on 130 problems.**
- **Data fidelity**: `Acc_τ = 1[max_i |(ŷ-y)/y| ≤ τ]` and `NMSE`,
  computed separately on the in-domain test set **and the held-out OOD set**.

**The best upstream result is about 31.5% symbolic accuracy**, with the budget standardized to **1000 LLM calls per problem**.

Good for: symbolic regression, equation discovery, memorization-resistant evaluation, in-domain vs. out-of-domain generalization.
Not good for: physical modeling that needs units/dimensions (**the benchmark has no dimensional information at all**).

## How Knosis uses it

- Exporter (`knosis/workspace/exporters/llm_srbench.py`): each task gets only its training data,
  `data/<name>/train.parquet` (columns = `symbols`), plus the variable descriptions; the true expression, `test` and `ood_test`
  stay in the raw HDF5. `dev` defaults to about 20% of tasks; `limit` samples test tasks. Needs `h5py` (`knosis[hdf5]`).
  Output: `predictions.jsonl` (one numpy expression per task).
- Scorer (`knosis/decision/llm_srbench.py`): evaluates the delivered expression on `test` (and `ood_test` when present).
  NMSE matches upstream `compute_output_base_metrics` (NaN predictions ignored); Acc_τ follows the paper's definition
  with τ = 0.1 (upstream code has no implementation). Reported: `acc_0.1`, `nmse_median`, `missing`, and for LSR-Synth
  `ood_acc_0.1` / `ood_nmse_median`. **Symbolic accuracy is not implemented** (it needs an LLM judge).
  A malformed expression counts as invalid (NMSE = inf) instead of crashing.
- Knowledge scorer: recomputes formula units (`form=formula` with `meta.task` / `meta.expression`) on held-out points
  and reports how many accepted equations hold and how many retracted ones indeed do not.

## Known issues

- **Gated download**; 401 is the most common first failure.
- **⚠️ OOD exists only for LSR-Synth.** In upstream code, asking an LSR-Transform problem for `ood_test_samples`
  **silently returns None instead of raising**, so code that assumes OOD everywhere breaks quietly.
- **The parquet and HDF5 files are easy to confuse**: the parquet looks like a complete dataset but **holds only metadata**;
  and since it is **regenerable**, it is easy to build a small dataset that "looks complete".
  Treating the parquet as the dataset gives you something "complete but without data".
- **Symbolic scoring strips constants**: a fit that is numerically excellent but has wrong constants still gets symbolic accuracy 1;
  conversely, the right structure with oddly placed constants may also be judged equivalent. **Do not use symbolic accuracy as numeric fidelity**;
  for the numeric track look at NMSE / Acc_τ.
- **⚠️ Split names differ in two places**: the CLI token is a **single word** (`lsrtransform`),
  while the HF split name **has underscores** (`lsr_transform`); upstream is inconsistent here, **do not normalize**.
- **Paper and disk problem counts differ**: paper 239, disk 240 (`lsr_synth_phys_osc` 44 vs 43).
- Upstream's `feynman` data module is **commented out**, so native Feynman evaluation does not work.
- Upstream's `root` argument is effectively **overridden** (`setup()` replaces `_dataset_dir` with the downloaded snapshot directory),
  so pointing it at a local copy has no effect.
- Each search method (**LLM-SR, LaSR, SGA, PySR**) needs **its own upstream package installed separately**;
  `requirements.txt` alone is not enough.
- **Variable metadata lacks three things**: units, a domain field, a complexity field; all must be supplied downstream.
  `symbol_properties` is free-form and **upstream has not published its vocabulary**; do not assume an enum.
