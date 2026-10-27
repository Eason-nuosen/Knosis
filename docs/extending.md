# Extending Knosis

Each kind of extension touches only one file or directory, plus a test that builds minimal data with `tmp_path`. Tests that need real data call `pytest.skip` when the data is absent.

## Adding a dataset (data layer)

1. `knosis/data/loaders/<name>.py`: a `load(scenario, root=None, **kw) -> Dataset`, registered with `@register("<name>", scenarios=...)`,
   and the module name added to the import list in `knosis/data/loaders/__init__.py`.
2. `knosis/data/cards/<name>.md`: a description for agents (source, layout, pitfalls); it **must not contain GT**. `knosis describe <name>` prints it.
3. Optional: a line in `SOURCES` in `knosis/data/download.py`; `datacards/<name>.md` with upstream source and license (for humans).

`Task.answer` holds GT (a value or a file path) and `Task.input` holds the task statement; GT does not go into `meta` unless the field name says it is a hint (e.g. BI-Bench's `oracle`).

## Opening workspaces on a dataset

Write `knosis/workspace/exporters/<name>.py`, decorate `export(ds, ws, write_data=True, **opts) -> dict` with `@register("<name>")`,
and add it to the import list at the end of `exporters/__init__.py`:

| Return key | Content |
| --- | --- |
| `brief` | Body of BRIEF.md (template in `workspace/templates/briefs/`; compute the facts from the data first, then write; say only that the data may contain noise, not how to handle it) |
| `tasks` | Test tasks (no answers), each with at least an `id`; written to `tasks/tasks.jsonl` only in the decide stage |
| `dev` | Dev tasks (no answers, disjoint from test tasks), used for feedback; may be empty |
| `holdout` | Task ids shown as examples in BRIEF and excluded from testing |
| `output` | Decide deliverable file name: `predictions.jsonl` (one `{id, answer}` per line) or `predictions.csv` (`row_id`, `prediction`, ...); None when there is no downstream prediction |
| `modalities` | Used to pick tools for TOOLS.md, e.g. `["graph"]`, `["table"]`, `["tables"]` |

With `write_data=False` it returns the above without writing data (used to regenerate tasks in the decide stage); the same `opts` must give the same split (`split()` splits by seed).
Put raw files into the workspace with `place()` (hard link, copy across filesystems); do not use symlinks, which expose the raw directory and the GT next to it.
On the command line, `ws init` passes `--dev` / `--limit` / `--seed` / `-o key=value` to the exporter.

## Adding an evaluation (decision layer)

Write a scorer in `knosis/decision/<name>.py`, register it, and add it to the import list at the end of `decision/__init__.py`:

```python
from . import register

@register("<name>")
def score(ws, state, ds, path, ids) -> dict:
    # path: deliverable file; ids: task ids to score (test or dev); ds: Dataset reloaded from the raw directory (with GT)
    return {"metrics": {...},                       # aggregate metrics
            "items": [{"id": ..., "ok": ..., "gold": ...}, ...],   # per-task results, returned to the agent as feedback (gold removed in score mode)
            "reference": {...}}                     # optional: trivial baselines
```

The same function serves `knosis eval` (test tasks) and `knosis feedback submit` (dev tasks).
To score whether the knowledge itself is correct (separately from whether it helps the task), optionally add `score_knowledge(ws, state, ds) -> dict` registered with `@register_knowledge("<name>")`;
its result goes into the `knowledge` section of the evaluation report and is never returned to the agent.

## Adding a tool (tool layer)

Create `knosis/tools/<name>/`:

- `TOOL.md`: YAML front matter `name / version / kind(program|model) / modality / stage / license`; the body covers purpose, example commands, output and limitations.
  The body is concatenated into the workspace's TOOLS.md, and the agent relies on it to decide whether to use the tool.
- `run.py`: command-line entry point with `--out DIR` for output; at the end call `knosis.tools.write_result(out, name, params, units, started)`,
  which writes `units.jsonl` (κ, `inferred` or `observed`, provenance starting with `tool:<name>@<version>(...)`) and `run.json`.
- `__init__.py` (empty), so tests can import it directly.

Tools do not modify data. Tools with heavy dependencies import them only on the real inference path and provide `--prepare-only`;
at run time `KNOSIS_<NAME>_PYTHON` selects the interpreter, and the core package does not install these dependencies.
Table tools can use `knosis.tools.read_tables(paths)` to read CSV / parquet uniformly.

## Adding a knowledge format (knowledge layer)

κ fields and checks live only in `knosis/knowledge/units.py`; ontology reading, writing, references, checks and conversion live only in `knosis/knowledge/ontology.py`.
For a new data source -> ontology conversion, write `from_<name>(ds) -> dict` (returning a core-layer document), reusing `from_tables` / `relationship` / `eob`,
and register it in `ontology convert` in `cli.py`.

Code style: short and direct, no defensive code; let errors raise.
