# KramaBench — end-to-end from data lake to insight (multi-source, heterogeneous)

## Source

MIT CSAIL. **KramaBench: A Benchmark for AI Systems on Data-to-Insight Pipelines over
Data Lakes**, arXiv **2506.06541** (2025-06-06), ICLR 2026.
Authors: Eugenie Lai, Gerardo Vitagliano, Ziyu Zhang … Michael Cafarella, Lei Cao,
Samuel Madden, Tim Kraska.
Repository https://github.com/mitdbg/KramaBench ;
data https://huggingface.co/datasets/eugenie-y/kramabench (lowercase b in the id).

Get it: `knosis download kramabench` (`git clone`, checkout about 640 MB).
Public, not gated, no application needed. **No PyPI package**; it can only be installed from the checkout.

**The licensing is messy; pay attention.**
- The GitHub repository **has no LICENSE file** → the code license is undeclared.
- The HF card's front-matter says `license: cc` (**no version number, no variant**).
- There is an **unmerged** HF community PR proposing a change to `cc-by-nc-4.0`, said to reflect the paper's terms.
- Some third-party sources say "MIT (code) + CC-BY-NC-4.0 (data)", but **no MIT text can be found anywhere in the repository**.

Practical judgment: **treat the data as CC BY-NC-4.0 (attribution + non-commercial)**, and treat the code as unlicensed.
If it matters to you, contact the authors directly to confirm.

Size (per the upstream README): 104 tasks, 633 subtasks, 1764 files, about 1.7 GB.
The actual checkout is about 640 MB (`data/*/raw/` is gitignored), so the number of files on disk
**will not equal 1764**. The latest commit changed legal after the README, so the subtask count also drifts slightly
(631 counted rather than 633); do not hard-code 1764 / 633.

## Description

KramaBench tests **starting from a pile of messy raw files and going all the way to a verifiable conclusion**.
Each task is "one question + one data lake directory", and the agent must find the files, decide on an approach, write code,
and compute the answer itself. So it evaluates two things at once: **the final answer**, and **whether the intermediate data pipeline is written correctly**.

6 domains: archaeology, astronomy, biomedical, environment, legal forensics, wildfire.
**The upstream directory name is `archeology` (misspelled, one a missing)**; it is part of the path, do not change it.
Likewise `environment` is "environment", not "environmental".

**⚠️ This description is deliberately restrained.** What this benchmark tests is the agent finding files on its own, judging on its own
which files are relevant, and designing the pipeline on its own. **Giving a file list, a field table, or recommending which files to use in advance
amounts to solving the task for it.** So Knosis only gives the data lake directory `ds.files["lake"]`, **with no parsing and no file list**.

Task structure: `workload/<domain>.json`; each task is
`{id, query, answer, answer_type, runtime, data_sources, subtasks[]}`.
Task ids look like `legal-hard-1`, subtasks `legal-hard-1-1`.
**The numbers in the ids are not contiguous** (`archeology-hard-1`, `archeology-hard-2`, `archeology-easy-3`, …);
do not assume a contiguous sequence. Also, **`data_sources` is a list at the task level but a bare string in some subtasks**;
a strict schema will break here.

Reference solutions are in `solutions/<domain>/<task id>.py`, all runnable Python, reading `./data/<domain>/input/`.
**There are no per-task validation scripts**; validation is centralized: the `answer_type` → metric mapping is hard-coded in
`benchmark/fixtures/answer_type_fixtures.json`. Answer types and corresponding metrics:

- `numeric_exact` → `success` (exact)
- `string_exact` → `success` (exact)
- `list_exact` → `f1` / `precision` / `recall`
- `numeric_approximate` → MAE / MSE / RAE
- `string_approximate` → `llm_paraphrase` (**calls an LLM: costs money, non-deterministic**)
- `list_approximate` → `f1_approximate` (**calls an LLM pair by pair**)

Besides the answer, `evaluator.py` also calls `llm_code_eval` to score **the pipeline itself**
(`pipeline_evaluation_engine`), then averages. So there are two readings; do not look only at answer accuracy.

Upstream also provides `dr-input/<domain>/<domain>-<difficulty>-<n>/`: each task's **oracle file subset**
(the "truth subset" retrieval setting). `eval.sh --use_truth_subset` takes this path,
**but this flag is not documented at all in the upstream README's parameter table**.

Good for: multi-source heterogeneous data ingestion, file format recognition, end-to-end pipeline design, autonomous agent exploration.
Not good for: loading everything at once with `datasets.load_dataset()`; **the HF viewer is broken**
(columns with the same name have inconsistent types across domains, and Arrow reports `float 1.5 truncated to int64`);
you must read per domain, or simply use the clone.

Pitfalls:
- **The HF dataset card is essentially empty**: its content is just those two front-matter lines, with no description at all.
- The upstream baseline (DS-GURU)'s `process_dataset` uses **non-recursive** `os.listdir`,
  so it cannot see the files in `data/astronomy/input/STORM-AI/warmup/v2/GOES/`;
  the astronomy domain goes from 1538 files to 10. **Recursion is your own responsibility.**
- `evaluate.py` writes `results/` into the repository, polluting a read-only install.
- The structure listing in the upstream README is wrong: it lists `results` (actually gitignored)
  but omits the `dr-input/`, `experts/`, `solutions/`, `tests/` that actually exist.
- The upstream repo's own citation block cites the wrong title (cited under another name); the arXiv title is authoritative.
- The best score on the upstream leaderboard is about 22%, while the paper reports 55%; the two use different retrieval / evaluation configurations and **cannot be compared directly**.
