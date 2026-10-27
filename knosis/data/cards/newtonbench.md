# NewtonBench — discovering physical laws from data (equation-type knowledge)

## Source

HKUST + NVIDIA. **NewtonBench: Benchmarking Generalizable Scientific Law Discovery in
LLM Agents**, arXiv **2510.07172** (v1 2025-10-08, v3 2026-02-24), ICLR 2026.
Authors: Tianshi Zheng, Kelvin Kiu-Wai Tam, Newt Hue-Nam K. Nguyen … Yangqiu Song, Ginny Y. Wong.
Repository https://github.com/HKUST-KnowComp/NewtonBench

**No HuggingFace dataset, no PyPI package, no downloadable data artifact of any kind.**
Only source code: `knosis download newtonbench` does a `git clone`.
The simulation environment uses numpy and **needs no API key to run** (but upstream's default evaluation uses an LLM as judge, and that step needs a key).

**License:** code **MIT** (LICENSE at the repository root); **paper CC BY-NC-SA 4.0** (non-commercial).
The two differ: reuse code under MIT, and mind the NC terms when citing the paper.

**⚠️ This benchmark has no "dataset" to load.** Tasks are generated at runtime by the harness:
the agent actively probes the simulator via the `<run_experiment>` tool (give a set of input parameters, get the output back),
and the ground-truth equations exist as Python functions in `modules/m*/laws.py`.
So this adapter reads **source code** and produces a physical schema of "variables + value distributions" and equation tasks.

Scale: 12 physical domains × 3 difficulties × 3 versions = **108 counterfactual laws**,
times 3 system complexities = **324 tasks**.

Get it: `knosis download newtonbench`

## Description

What NewtonBench tests: **having the agent actively run experiments and infer the underlying physical law from observed data.**

It differs fundamentally from common symbolic regression benchmarks (the Feynman / SRBench kind):
**it does not give you input data points.** The agent must design the experiments itself: choose a set of input parameters,
call the simulator, get the output, then decide what to ask next. This is "active experimental design", not "fitting given data".

**12 physical domains** (directory name → physics content):
`m0_gravity` universal gravitation, `m1_coulomb_force` Coulomb force, `m2_magnetic_force` Ampère force,
`m3_fourier_law` Fourier heat conduction, `m4_snell_law` Snell refraction, `m5_radioactive_decay` radioactive decay,
`m6_underdamped_harmonic` underdamped harmonic oscillation, `m7_malus_law` Malus's law, `m8_sound_speed` speed of sound,
`m9_hooke_law` Hooke's law, `m10_be_distribution` Bose-Einstein distribution, `m11_heat_transfer` heat transfer.

**Two orthogonal dimensions; it is easy to count only one:**
- **Difficulty** `easy` / `medium` / `hard`: determined by **the number of mutations applied to the expression** (mutations accumulated starting from the canonical law).
- **Version** `v0` / `v1` / `v2`: different mutations at the same difficulty. In `evaluation_results/`,
  `{difficulty}/{version}` are two nested directory levels. **Reading it as "12 domains × 3 difficulties = 36" undercounts by a factor of 3.**

Mutations are **cumulative**: easy = 1–2 mutations from the canonical law; medium = easy plus 1–2 more; hard adds further.
Mutation operations act on the expression tree (swapping operators, e.g. `+` → `×`; changing constants / exponents, e.g. square → cube).
There are four curation rules: no new variables are introduced, complexity does not decrease, a mutation cannot be the inverse of the previous one, and two consecutive mutations cannot be equivalent to a single mutation.

**⚠️ Every target law embeds at least one "rescaled physical constant"**, to restore the dimensional consistency broken by mutation.
It appears in the source as `HIDDEN_CONSTANT`, e.g. `6.674e-5` for `m0_gravity`.
**This is not the real gravitational constant; do not "correct" it.** It is exposed in the prompt as `HIDDEN_CONSTANT_C`,
and it must not be used as a function parameter (it is required to be defined as a local variable inside the function body).

**⚠️ Three system complexity levels**: `vanilla_equation` (pure equation) / `simple_system` / `complex_system`.
The latter two add "auxiliary equations": the auxiliary equations are told to the agent, the target law is not.
Simple averages 1.75 auxiliary equations / 5.17 operations; Complex averages 2.42 / 8.17.

**Variables and value domains**: variable names and meanings are **prose descriptions** (`PARAM_DESCRIPTION` strings),
and value domains follow a **log-uniform sampling** convention, e.g. the two masses of `m0_gravity` are `U_log(10^0, 10^3)`,
and the distance is `U_log(1, 10^1)`. In the source it is literally `np.exp(np.random.uniform(np.log(1), np.log(1e3)))`.

**⚠️ No units / dimension metadata.** There is no structured table of units or dimensions anywhere in the repository;
units appear only in **comments on tolerance constants** (like `1e-9  # meters`).
So the "physical schema + dimensions" envisioned in the plan **has to be supplied by us** for this benchmark;
Knosis here faithfully gives only "variable name + meaning + sampling distribution", and marks dimensions as missing.

Scoring (two tracks, do not mix them up):
- **Symbolic Accuracy (SA)**: binary, using **an LLM as judge** of symbolic equivalence,
  **deliberately ignoring physical constants**. The judge defaults to `nemotron-ultra` (the paper reports 98.3% agreement with humans).
  The judge tolerates variable renaming and rewritten constants, but **not changed exponents** ("exponents 4 and 4.03 count as different").
  **It cannot run offline; this step needs an API.**
- **RMSLE**: data fidelity, computed on **5000 held-out samples**, with Modified Z-Score outlier removal.
  Upstream **explicitly rejected NMSE** in favor of RMSLE.

Good for: active experimental design, symbolic regression, counterfactual reasoning, dimensional analysis.
Not good for: reading it as an ordinary x/y tabular dataset; **there is no such table on disk**.

Pitfalls:
- **The ground truth is in the code**: `LAW_REGISTRY` in `modules/m*/laws.py`, with the structure `{'easy': {'v0','v1','v2'}, ...}`.
  **There is no export format** (no JSON manifest); to turn it into a data artifact you have to export it yourself.
- **The ground-truth function signature differs from the one shown to the LLM**: internally it is
  `_ground_truth_law_easy_v0(mass1, mass2, distance)`, while submissions must be
  `def discovered_law(...)`, bridged by `parameter_mapping`.
- **Some laws are physically implausible** (explicitly acknowledged in the upstream paper): mutations guarantee dimensional self-consistency, but some forms
  do not hold in our universe. For example, some hard variants of `m8` and `m10`:
  **certain inputs produce NaN / inf**; the code has guard clauses and `float('nan')` branches,
  and the metrics code filters them out explicitly. Do not treat these as load failures.
- **Randomness**: `core.py` uses bare `np.random.uniform` with no visible global seed;
  the paper's numbers are the mean and standard deviation of **four runs**. Reproducibility is not guaranteed by default.
- Upstream reports: noise of even 0.0001 lowers SA by 12–16%;
  **giving strong models code assistance actually lowers performance** (a shift from exploration to exploitation), while weak models improve.

Terminology: "law" here means a physical law that can be written as an equation; "counterfactual" means a version of a canonical law that has been mutated.
