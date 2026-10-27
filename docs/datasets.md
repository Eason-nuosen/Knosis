# Datasets

All 13 dataset entries can open a workspace and be evaluated (`knosis ws init <dataset> <scenario>` -> four stages -> `knosis eval`).
Data lives in `data/<name>/` under a source checkout, or `~/.knosis/data/<name>/` when installed with `pip install knosis`; set `KNOSIS_DATA_DIR` to put it elsewhere. `knosis download <name>` fetches it.
`knosis describe <name>` prints the agent-facing card (source, layout, pitfalls; `knosis/data/cards/`); upstream sources and licenses are in `datacards/`.

| Dataset | Scenario | Deliverable | Metrics (the offline-computable part) | Dev (feedback) | Limitations |
| --- | --- | --- | --- | --- | --- |
| ngdbench | ngd-fin | answer JSONL (optionally with noise assertions) | answer-set EM / F1; noise assertion P/R; reference: copying answers from the noisy graph | 50 tasks; demo task sets of 10 / 20 | Many NL statements disagree with their Cypher, see [demos](demos.md); only ngd-fin has a BRIEF template, so the other NGDBench domains cannot open workspaces |
| tabarena | 51 datasets | prediction CSV | RMSE / accuracy / AUC / log loss; reference: training prior | 0 by default, `--dev N` holds out training rows | - |
| relbench | database name, `-o task=` | prediction CSV | AUROC / MAE / MAP@k; reference: trivial baselines | val split | - |
| bibench | case id or `all` | table JSONL | upstream matching rule success; `-o metadata=true` provides an initial ontology | 20 cases in `all` mode | - |
| kramabench | domain | answer JSONL | upstream exact / approximate / list F1 | about 25% | Metrics that need an LLM judge fall back to normalized exact match |
| burr | real database / micro scenario / `micro/<category>` | mapping JSONL | upstream class / relation / attribute P/R/F1 | about 25% with multiple scenarios | No scoring against the D2RQ GT of iswc and npd |
| llm-srbench | split | expression JSONL | NMSE, Acc₀.₁ (including OOD) | about 20% | No symbolic equivalence (needs an LLM) |
| newtonbench | domain | law function source | upstream RMSLE; experiments via the `newton` tool | whole (difficulty, version) groups | No symbolic equivalence (needs an LLM) |
| alphabench | evaluate (CSI300) | factor judgment JSONL | signal accuracy, IC MAE / Spearman, per-dimension scores | 50 tasks | No generate task (needs IC computed with Qlib); no US equities |
| spreadsheetbench | all / cell / sheet | output xlsx for each of an instruction's 3 test cases | upstream cell value comparison (formulas recalculated with LibreOffice before scoring): soft / hard; reference: returning the input unchanged | split by instruction, dev 5 / test 15 by default | .xlsm skipped by default; requires LibreOffice |
| text | corpus path | none (knowledge layer only) | unit count, locatable-provenance rate, citation checks | none | - |
| traces | name, `-o paths=` traces (Codex / Claude Code including subagents / step-by-step logs / messages / ATIF), optional `-o env=` | none (knowledge layer only) | valid cited-step rate, environment re-check rate, share checked against traces only | none | Transfer benefit is measured separately: merge into a knowledge base and compare on new tasks |
| whoandwhen | all / algorithm / hand | JSONL with the failing agent and step for each failure log | upstream agent-level / step-level accuracy; reference: random guess | split by log, dev 10 / test 30 by default | `-o answer=true` provides the task's reference answer (the with-ground-truth setting) |

Traces (`traces`, `whoandwhen`, `kb collect`) are all stored as ATIF v1.7 (`<id>.json` + `.md`, format in `knosis/data/traces.py`),
cited as `<dir>/<id>.json#step/<n>`; `knosis migrate` converts traces stored as older step sequences (rewriting cited step numbers too).

## Python API

```python
from knosis import load_dataset, list_datasets, describe

list_datasets()          # the 13 dataset entries
describe("ngdbench")     # agent-facing description (source / layout / pitfalls), no GT
ds = load_dataset("ngdbench", "ngd-fin")
ds.tasks[0]              # Task(id, input, answer, split, kind, meta); answer is GT, read only at evaluation
g = ds.read("clean")     # opens by suffix: parquet/csv -> DataFrame, gpickle -> graph ...
```

```python
from knosis.knowledge import check_knowledge, ontology

check_knowledge("ws/x", root="ws/x")                      # κ structure + evidence consistency + ontology refs + dedup aliases and conflict marks
model = ontology.from_bibench(load_dataset("bibench", "101248502"))   # Power BI metadata -> ontology core layer
ontology.write_ontology("onto/", {"semantic_model": model})
ontology.ontology_units(ontology.load_ontology("onto/"))  # expand ontology elements into κ (form=schema)
```

```bash
knosis ontology convert relbench rel-f1 --out onto/f1    # primary / foreign keys from the manifest -> core layer
knosis ontology check onto/f1
knosis ontology units onto/f1                            # print the κ view of the ontology
```
