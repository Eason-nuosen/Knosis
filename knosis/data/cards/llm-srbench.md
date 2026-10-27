# LLM-SRBench — a memorization-resistant symbolic regression benchmark

## Source

Virginia Tech / VinUniversity / CMU. **LLM-SRBench: A New Benchmark for Scientific Equation
Discovery with Large Language Models**, arXiv **2504.10415** (2025-04-14, v2 2025-06-07),
**ICML 2025 Oral**.
Authors: Parshin Shojaee, Ngoc-Hieu Nguyen, Kazem Meidani, Amir Barati Farimani, Khoa D Doan, Chandan K Reddy.
Repository https://github.com/deep-symbolic-mathematics/llm-srbench ;
data https://huggingface.co/datasets/nnheui/llm-srbench

Get it: `knosis download llm-srbench`
(internally uses direct HF access; upstream uses `snapshot_download`, which fetches it itself.)

**⚠️ The data is gated (`gated: "auto"`).** Anonymous access to `resolve/main/...` returns **401**,
so CI must have `HF_TOKEN`, and you must first accept the terms on the HF web page. This is the step where people most often get stuck.

**License:** code **MIT**; paper **CC BY 4.0**;
**but the HF data artifacts themselves have no license field at all**: undeclared. If it matters to you, contact the authors.

Very small (metadata) plus a large file: 5 parquet files totaling about 36 KB, plus a **239 MB** HDF5.
**⚠️ The paper says 239 questions; on disk there are 240** (the physics split has 44 rather than 43);
the cause of the one-question difference is unknown; if you need the question count to match exactly, diff the `phys_osc` names yourself.

## Description

What LLM-SRBench tests: **inferring the underlying scientific equation from given input-output data.**

How it differs from NewtonBench: **here you are given data** (no need to run experiments actively),
but its core contribution is **memorization resistance**: the questions are not copied directly from textbooks
but constructed, to prevent an LLM from passing off recalled answers as "discovery".

**Two construction routes with different properties:**
- **LSR-Transform** (111 questions): take 100 classic Feynman equations, turn one **input variable into the target**,
  and solve symbolically with SymPy to get a new equation. Only analytically solvable transformations are kept, data points are projected into the valid domain of the new equation,
  and complexity is kept within the node-count distribution of the original Feynman equations. This is physics.
- **LSR-Synth** (129 questions): GPT-4o first generates **known terms** and **synthetic novel terms** for a scientific problem,
  then `solve_ivp` checks solvability, GPT-4o checks novelty, data points are generated,
  and finally **two domain experts manually verify** the expressions and data-point plots. Four domains: chemistry 36, biology 24, physics 44, materials 25.

**The data lives in two places; do not look only at the parquet:**
- **The parquet holds only metadata**: five files, with columns
  `name` / `symbols` / `symbol_descs` / `symbol_properties` / `expression`.
  **There is no numeric data in them at all.** If you assume the parquet is the dataset, you will find it "very complete but with no data".
- **The numbers are in the HDF5** (`lsr_bench_data.hdf5`, 239 MB). Group paths:
  - LSR-Transform: `/lsr_transform/{name}`
  - LSR-Synth: `/lsr_synth/{dataset}/{name}`, e.g. `/lsr_synth/bio_pop_growth/BPG0`
  The dataset keys within each group are `train` / `test` / `ood_test` (`ood_test` exists only for LSR-Synth).
  Knosis puts the group path in `task.meta["hdf5_group"]`; fetch data with `ds.read("hdf5")[group]["train"]`.

**⚠️ OOD exists only for LSR-Synth.** For LSR-Transform questions, accessing `ood_test_samples`
**silently returns None instead of raising an error**; code that assumes OOD is everywhere will quietly go wrong.

**Variable metadata has names and meanings (`symbols` + `symbol_descs`), but no units.**
No units field, no dimensions, no SI annotations: none of these appear anywhere in the schema.
`symbol_properties` is a free-form list of strings (encoding variable roles / flags);
**upstream has not published its value vocabulary**, so do not assume a fixed enumeration.

There is also no `domain` field and no `complexity` field: the domain is determined by which split you load;
complexity can only be computed yourself (e.g. running sympy's `count_ops` on `expression`).

Scoring (two tracks):
- **Symbolic accuracy**: GPT-4o acts as a judge of mathematical equivalence, **after stripping parameters and constants**.
  Agreement with two human annotators on 130 questions is 94.6%.
- **Data fidelity**: `Acc_τ = 1[max_i |(ŷ-y)/y| ≤ τ]` and `NMSE`, computed separately on the in-domain test set
  **and the held-out OOD set**.
- The best upstream result is about **31.5%** symbolic accuracy, with the budget standardized to 1000 LLM calls per question.

Good for: symbolic regression, equation discovery, memorization-resistant evaluation, comparing in-domain and out-of-domain generalization.
Not good for: physical modeling that needs units / dimensions (this benchmark contains no dimensional information at all).

Pitfalls:
- **Gated download**; 401 is the most common first failure.
- **The parquet and HDF5 files are easily confused**: the parquet looks like a complete dataset but holds only metadata;
  and this parquet is regenerable, so it is easy to produce a small dataset that "looks complete".
- **Symbolic scoring strips constants**: an excellent numeric fit with wrong constants still gets symbolic accuracy 1;
  conversely, a correct structure with oddly placed constants may also be judged equivalent. **Do not use symbolic accuracy as numeric fidelity**;
  for the numeric track look at NMSE / Acc_τ.
- Upstream's `feynman` data module is **commented out**, so the native Feynman evaluation does not work.
- Upstream's `root` parameter is in fact **overridden** (`setup()` replaces `_dataset_dir` with the downloaded snapshot directory),
  so pointing it at a local copy has no effect.
- Each search method (LLM-SR, LaSR, SGA, PySR) requires **installing its upstream package separately**;
  installing only `requirements.txt` is not enough.
