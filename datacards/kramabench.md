# KramaBench

| Item | Value |
| --- | --- |
| Paper | KramaBench: A Benchmark for AI Systems on Data-to-Insight Pipelines over Data Lakes |
| arXiv | **2506.06541** (2025-06-06); ICLR 2026 |
| Authors | Eugenie Lai, Gerardo Vitagliano, Ziyu Zhang … Michael Cafarella, Lei Cao, Samuel Madden, Tim Kraska (MIT CSAIL) |
| Code | https://github.com/mitdbg/KramaBench |
| Data | https://huggingface.co/datasets/eugenie-y/kramabench (**lowercase b in the id**) |
| Access | Public, not gated, no request needed |
| **License** | **Code not declared** / data treated as **CC BY-NC-4.0** (see below) |
| Upstream version | **No release tags**; `pyproject.toml` says `1.0.0.dev0`. Observed clone single commit `b2e0d77540263f8b6119f977fe79a8c4386b5a02` (`Updates to legal-hard-29`) |

## License

**The licensing is muddled; be careful.**

- The GitHub repo **has no LICENSE file**: verified, `ls -a | grep -iE "licen|copying"` returns nothing
  -> **code license not declared**.
- The HF card front-matter says `license: cc` (**no version, no variant**).
- An **unmerged** HF community PR proposes changing it to `cc-by-nc-4.0`, saying this reflects the paper's terms.
- Third-party sources say "MIT (code) + CC-BY-NC-4.0 (data)",
  but **no MIT text can be found anywhere in the repo**.

Practical judgment: **treat the data as CC BY-NC-4.0 (attribution + non-commercial)** and the code as unlicensed.
Contact the authors directly if this matters to you.

## Obtaining

```bash
knosis download kramabench              # git clone (--depth 1) the upstream repo
```

**All data is in the git repo.** No pip package, no release, no request form.
A clone gives you all of `workload/*.json`, `solutions/`, the data lake and the evaluator.

**⚠️ Do not load it in one go with `datasets.load_dataset("eugenie-y/kramabench")`.**
**The HF viewer is broken**: same-named columns have inconsistent types across domains,
and Arrow fails with `float 1.5 truncated to int64`.
Read each domain separately, or just use the clone (recommended).

Upstream evaluation entry point:

```bash
python evaluate.py --sut YourSUT --workload legal --verbose
```

`evaluate.py` produces:

```
results/<SUT>/<workload>_measures_<timestamp>.csv   # fine-grained metrics
results/aggregated_results.csv                      # one summary row per domain
```

## Size

**As stated in the upstream README** (its "Breakdown of tasks per domain" table):

| Domain | Tasks | Subtasks | % Hard | Files | Raw size |
| --- | ---: | ---: | ---: | ---: | ---: |
| Archaeology | 12 | 71 | 50 % | 5 | 7.5 MB |
| Astronomy | 12 | 68 | 50 % | 1 556 | 486 MB |
| Biomedical | 9 | 38 | 67 % | 7 | 175 MB |
| Environment | 20 | 148 | 70 % | 37 | 31 MB |
| Legal | 30 | 188 | 53 % | 136 | 1.3 MB |
| Wildfire | 21 | 120 | 71 % | 23 | 1 GB |
| **Total** | **104** | **633** | **61 %** | **1 764** | **1.7 GB** |

**The actual checkout is about 640 MB**: verified with `du -sh data/*` in the checkout:

```
7.2M   data/archeology
486M   data/astronomy
86M    data/biomedical
30M    data/environment
1.2M   data/legal
30M    data/wildfire
```

`data/*/raw/` is gitignored, so **the file count on disk will not equal 1764**.

**⚠️ Subtask counts drift.** Measured over the six workload files:
`71 + 68 + 38 + 148 + 186 + 120 = 631` (README says 633; Legal says 188 but measures **186**):
legal was edited after the README (the latest commit is `Updates to legal-hard-29`).
**Do not hardcode 1764 / 633.**

Measured file counts (`data/<domain>/input/`, recursive):

| Domain | Files on disk |
| --- | ---: |
| archeology | 5 |
| astronomy | **1 538** |
| biomedical | 8 |
| environment | 37 |
| legal | 132 |
| wildfire | 22 |

Extension distribution (all six domains):

| Extension | Count |
| --- | ---: |
| `.csv` | 1 626 |
| `.sp3` | 37 |
| `.hdr` | 37 |
| `.txt` | 18 |
| `.xlsx` | 10 |
| `.dat` / `.tle` / `.lst` / `.gpkg` | 2 each |
| `.npz` / `.cdf` / `.text` / `.html` / `.py` / `.json` | 1 each |

**Why the astronomy directory and the measured file count disagree**: the upstream baseline (DS-GURU)
`process_dataset` uses **non-recursive** `os.listdir` and cannot see the files under
`data/astronomy/input/STORM-AI/warmup/v2/GOES/`, so astronomy shrinks from 1538 files to 10.
**Recursion is your responsibility.**

**`answer_type` distribution** (measured, task level):

| Domain | answer_type |
| --- | --- |
| archeology | `numeric_exact` ×10, `string_exact` ×2 |
| astronomy | `numeric_exact` ×8, `list_approximate` ×2, `string_approximate` ×1, `list_exact` ×1 |
| biomedical | `numeric_exact` ×6, `list_exact` ×2, `string_exact` ×1 |
| environment | `numeric_exact` ×11, `string_exact` ×4, `list_exact` ×3, `string_approximate` ×2 |
| legal | `numeric_exact` ×15, `string_exact` ×8, `string_approximate` ×3, `list_exact` ×3, `numeric_approximate` ×1 |
| wildfire | `string_exact` ×5, `numeric_approximate` ×5, `numeric_exact` ×4, `string_approximate` ×4, `list_exact` ×3 |

## Layout

```
KramaBench/
├── benchmark/                    # evaluator code
│   ├── evaluator.py
│   ├── executor.py
│   ├── metrics.py
│   └── fixtures/
│       ├── answer_type_fixtures.json      # answer_type -> metrics, hardcoded here
│       ├── input_type_fixtures.json
│       ├── output_type_fixtures.json
│       └── task_fixtures.json
├── data/
│   └── <domain>/input/<raw files>   # data lake (⚠️ the domain directory is spelled archeology, see below)
├── dr-input/<domain>/<domain>-<difficulty>-<n>/  # per-task oracle file subset (truth subset)
├── experts/                      # ⚠️ missing from the upstream README's structure listing
├── quickstart/
├── scripts/
├── solutions/<domain>/<task id>.py  # reference solutions, all runnable Python
├── systems/                      # baseline systems
├── tests/                        # ⚠️ also missing from the README's structure listing
├── utils/
├── workload/
│   ├── archeology.json
│   ├── astronomy.json
│   ├── biomedical.json
│   ├── environment.json
│   ├── environment-tiny.json     # -tiny samples, not part of the official evaluation
│   ├── legal.json
│   ├── legal-tiny.json
│   └── quick-start-questions.json
├── eval.sh
├── evaluate.py
├── pyproject.toml
└── version.bash
```

Directory conventions (**upstream spelling, do not change**):

```
data/<domain>/input/<raw files>                    : data lake
workload/<domain>.json                             : task definitions
solutions/<domain>/<task id>.py                    : reference solutions
dr-input/<domain>/<domain>-<difficulty>-<n>/       : per-task oracle file subset (truth subset)
```

**⚠️ `results/` is not listed above**: it is gitignored and only created when evaluation runs.
The upstream README's structure listing includes it, while omitting the existing
`dr-input/`, `experts/`, `solutions/`, `tests/`.

**⚠️ `data/*/raw/` is also gitignored**, so no raw directories appear in the checkout.

## Task structure

`workload/<domain>.json` is a JSON array whose elements are
`{id, query, answer, answer_type, runtime, data_sources, subtasks[]}`.
Measured wildfire task keys: `answer, answer_type, data_sources, deepresearch_subset, id, query, runtime, subtasks`;
subtask keys: `answer, answer_type, data_sources, id, query, step`.

Task ids look like `legal-hard-1`, subtasks like `legal-hard-1-1`.

**⚠️ The numbers in ids are not contiguous by difficulty.** The first 12 in legal:
`legal-hard-1`, `legal-hard-2`, `legal-easy-3`, `legal-easy-4`, `legal-easy-5`,
`legal-hard-6`, `legal-hard-7`, `legal-hard-8`, `legal-easy-9`, `legal-easy-10`,
`legal-easy-11`, `legal-easy-12`: difficulty **jumps around**; do not assume a contiguous sequence.

**⚠️ `data_sources` has an unstable type.** Measured: at task level **104 / 104 are lists**;
at subtask level **557 lists, 71 bare strings, 3 `null`**.
The bare strings are concentrated in archeology.
**A strict schema will break here.**

**⚠️ `runtime` is always `1`** (measured over every task in all six domains): do not use it as a real time limit.

The `deepresearch_subset` field is present on **all 104 tasks** (measured 12/12, 12/12, 9/9,
20/20, 30/30, 21/21). Upstream uses it to mark the "deep research subset" questions; useful for stratified evaluation.

## Metrics

The `answer_type` -> metric mapping is **hardcoded in `benchmark/fixtures/answer_type_fixtures.json`**
(measured: exactly the six entries below; `metrics` is a list):

| answer_type | Metrics | Notes |
| --- | --- | --- |
| `numeric_exact` | `success` | Exact numeric: correct within **relative error 1e-6 or absolute 1e-4** |
| `string_exact` | `success` | Exact string (**case-insensitive**) |
| `numeric_approximate` | `mean_absolute_error` / `mean_squared_error` / `rae_score` | Approximate numeric |
| `string_approximate` | `llm_paraphrase` | Approximate string: **an LLM judges paraphrase (costs money, nondeterministic)** |
| `list_exact` | `f1` / `precision` / `recall` | Exact list: set F1 |
| `list_approximate` | `f1_approximate` | Approximate list: **an LLM judges each pair** |

**Besides the answer, upstream `evaluator.py` also calls `llm_code_eval` to score the pipeline itself**
(`pipeline_evaluation_engine`), and averages at the end.
So upstream **has two readings; do not look only at answer accuracy**.

The upstream README also mentions **BLEU / ROUGE** (strings) and a **bootstrapped rubric** (partial credit),
plus the task types in `benchmark/fixtures/task_fixtures.json`
(`extraction` / `calculation` / `prediction` / `summarization` / `complex_qa` / `explanation`).
Note that `--skip_subtasks` evaluates only the final answer (fast, but less informative).

**⚠️ `eval.sh --use_truth_subset` takes the `dr-input/` path,
but this flag is not documented in the upstream README's argument table at all.**
`eval.sh` also hardcodes the conda environment name `smol311` and an SUT name; edit them before use.

## How Knosis uses it

- Loader (`knosis/data/loaders/kramabench.py`): scenario is a domain (`archeology`, `astronomy`, `biomedical`,
  `environment`, `legal`, `wildfire`; default `wildfire`). One task per entry in `workload/<domain>.json`;
  `query` is the input, `answer` the answer, `answer_type` the kind; subtasks and the path to
  `solutions/<domain>/<task id>.py` go into `meta`. Files are deliberately not listed per task: finding them is part of the task.
- Exporter (`knosis/workspace/exporters/kramabench.py`): the agent gets the whole data lake (`data/<domain>/input/`,
  copied recursively) and the questions, plus each answer's shape (numeric / string / list, without exact / approximate).
  Answers, reference solutions and subtasks stay in the raw directory. `dev` defaults to about 1/4 of tasks (at least 1).
  Output: `predictions.jsonl`.
- Scorer (`knosis/decision/kramabench.py`): ports the **non-LLM** metrics of upstream `benchmark/metrics.py`
  and scores **final answers only** (no pipeline scores, no subtasks):
  - `numeric_exact` / `string_exact`: upstream Success (numbers tolerate rounding error, strings case-insensitive);
  - `numeric_approximate`: upstream RAE score = 1 / (1 + relative error); ok means relative error ≤ 1%;
  - `list_exact`: upstream F1 (strings case-insensitive, numbers relative error < 1e-6);
  - `list_approximate`: upstream F1Approximate with numeric relative error ≤ 1%;
  - `string_approximate` and string elements of `list_approximate`: upstream uses an LLM paraphrase judge;
    Knosis falls back to exact match after normalization (alphanumerics only, lowercase).

  Reported: `accuracy`, `score`, `missing`, `by_answer_type` (n / accuracy / score per type), and a `note` on the LLM fallback.

## Known issues

- **The upstream directory name is `archeology` (misspelled, missing an a)**: verified that
  `data/`, `solutions/`, `dr-input/`, `workload/` all use this spelling.
  **It is part of the path; do not change it.**
- Likewise `environment`, not `environmental`.
- **The HF dataset card is essentially empty**: only the two front-matter lines, no description.
- **The upstream baseline (DS-GURU) `process_dataset` uses non-recursive `os.listdir`**:
  see "Size"; astronomy shrinks from 1538 files to 10. **Recursion is your responsibility.**
- **`evaluate.py` writes `results/` into the repo, polluting read-only installs.**
- **The upstream README's structure listing is wrong**: it lists `results` (actually gitignored)
  and omits the existing `dr-input/`, `experts/`, `solutions/`, `tests/`.
- **The upstream repo's own citation block cites the wrong title** (a different name);
  use the arXiv title.
- **The best upstream leaderboard score is about 22%, while the paper reports 55%**:
  the retrieval/evaluation setups differ, **so they are not directly comparable**.
  (The README leaderboard hardcodes scores for GPT-o3 / GPT-4o / Claude-3.5 /
  Llama-3 Instruct / DeepSeek-R1 / Qwen-2 Coder; the GPT-o3 row of `DS-GURU (self-correcting)`
  is highest, **22.08 % overall**.)
- **No PyPI package**; install only from the checkout (`pip install .` / `pip install ".[baselines]"`).
  `pyproject.toml` has `version = "1.0.0.dev0"` and `requires-python = ">=3.10"`.
- **`workload/*obscured*` and `data/*obscured*` are gitignored**:
  upstream has "obscured" workloads and datasets that you will not see locally.
- **The data lake contains executable scripts** (measured: wildfire has `load_data.py` and an `.html`);
  when scanning files, do not mistake upstream helper scripts for data files.
- **Formats such as `.sp3` / `.hdr` / `.tle` / `.gpkg` / `.cdf` / `.npz` make up most of astronomy**:
  pandas alone cannot read them; budget time for parsing.
