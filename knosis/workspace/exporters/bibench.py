"""BI-Bench: multi-table business QA over real Power BI projects. scenario is a case id, or `all` (all 100 cases together)."""

from __future__ import annotations

from pathlib import Path

from ...data import load_dataset
from ...knowledge import ontology
from ...lang import t
from . import place, register, render, split


def merged_ontology(ds) -> dict:
    """Merge the core layers of all cases: prefix dataset names with the case id so same-named tables from different cases do not collide."""
    datasets, relationships = [], []
    for task in ds.tasks:
        model = ontology.from_bibench(load_dataset("bibench", task.id, root=ds.root.parent))
        prefix = f"c{ontology.snake(task.id)}_"
        for d in model["datasets"]:
            datasets.append({**d, "name": prefix + d["name"], "source": f"{task.id}/{d['source']}"})
        for r in model.get("relationships", []):
            relationships.append({**r, "name": prefix + r["name"], "from": prefix + r["from"], "to": prefix + r["to"]})
    return ontology.semantic_model("bibench_all", datasets, relationships,
                                   provenance={"method": "converted", "author": "knosis.from_bibench"},
                                   source={"dataset": "bi-bench", "item": "all"})


@register("bibench")
def export(ds, ws: Path, write_data=True, dev=None, limit=None, seed=0, metadata=False, **opts) -> dict:
    """`dev` default: 20 cases in all mode, 1 in project mode (scenario is a project id), 0 for a single case.
    With `metadata=true`, convert the Power BI model metadata into an ontology in the initial knowledge layer."""
    ws = Path(ws)
    single = len(ds.tasks) == 1
    tasks = [{"id": t.id, "question": t.input, "tables": f"data/{t.id}/"} for t in ds.tasks]
    default = 0 if single else 20 if ds.scenario == "all" else 1
    dev_tasks, tests = split(tasks, default if dev is None else dev, limit, seed)
    lines = []
    for task in ds.tasks:
        csvs = sorted(Path(task.meta["dir"]).glob("*.csv"))  # Tables only; oracle, transformation/ and join/ are hints and are not exported
        if write_data:
            for f in csvs:
                place(f, ws / "data" / task.id / f.name)
        stems = f"{', '.join(f.stem for f in csvs[:8])}{' …' if len(csvs) > 8 else ''}"
        lines.append(t(f"- `data/{task.id}/`: {len(csvs)} tables ({stems})",
                       f"- `data/{task.id}/`：{len(csvs)} 张表（{stems}）"))
    if write_data and metadata:
        model = ontology.from_bibench(ds) if single else merged_ontology(ds)
        ontology.write_ontology(ws / "kb/knowledge/ontology", {"semantic_model": model})
    brief = render(
        "bibench.md", n_cases=len(ds.tasks), cases="\n".join(lines), n_dev=len(dev_tasks), n_test=len(tests),
        metadata=t("`kb/knowledge/ontology/` already holds an ontology core layer converted from the original Power BI project's model metadata"
                   " (tables, columns, DAX of calculated columns, table relationships defined by the project author); you may adopt, revise or retract it.",
                   "`kb/knowledge/ontology/` 里已有一份由原 Power BI 项目模型元数据转换来的本体 core 层"
                   "（表、列、计算列的 DAX、项目作者定义的表间关系），可以采用、修订或撤回。")
        if metadata else t("The original BI project's model metadata (table relationships etc.) is not provided; infer it from the data yourself.",
                           "没有提供原 BI 项目的模型元数据（表间关系等），需要自己从数据里判断。"),
    )
    return {"brief": brief, "tasks": tests, "dev": dev_tasks, "holdout": [],
            "output": "predictions.jsonl", "modalities": ["tables"]}
