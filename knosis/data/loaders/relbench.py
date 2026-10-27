"""RelBench: entity-level prediction tasks on relational databases, split by time.

    data/relbench/<db>/{manifest.yaml, db/<table>.parquet, tasks/<task>/{manifest.yaml,train,val,test}.parquet}
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..dataset import Dataset, Task, data_dir
from . import register

DBS = ("rel-amazon", "rel-avito", "rel-event", "rel-f1", "rel-hm", "rel-stack", "rel-trial")

METRICS = {
    "roc_auc": "binary AUROC",
    "map": "recommendation MAP",
    "nmae": "regression normalized MAE (lower is better)",
    "delta_with_knowledge": "metric difference with vs. without Knosis knowledge",
}


@register("relbench", scenarios=DBS)
def load(scenario: str = "rel-f1", root: str | Path | None = None, task: str | None = None) -> Dataset:
    ddir = Path(root or data_dir("relbench")) / scenario
    schema = yaml.safe_load((ddir / "manifest.yaml").read_text())
    files = {p.stem: p for p in sorted((ddir / "db").glob("*.parquet"))}

    tasks = []
    for tdir in sorted(p for p in (ddir / "tasks").iterdir() if (p / "manifest.yaml").is_file()):
        if task and tdir.name != task:
            continue
        spec = yaml.safe_load((tdir / "manifest.yaml").read_text())
        for split in ("train", "val", "test"):
            if (tdir / f"{split}.parquet").is_file():
                tasks.append(Task(
                    id=f"{scenario}/{tdir.name}/{split}",
                    input=spec.get("description", ""),
                    answer=tdir / f"{split}.parquet",
                    split=split,
                    kind=spec.get("task_type", ""),
                    meta=spec,
                ))

    return Dataset("relbench", scenario, ddir, files=files, schema=schema, tasks=tasks, metrics=METRICS)


def task_splits(ds: Dataset, task: str | None = None) -> dict[str, Task]:
    """{train / val / test: Task} for one task; `task` defaults to the first task. Task.answer is the path to that split's label table."""
    name = task or ds.tasks[0].meta["name"]
    return {t.split: t for t in ds.tasks if t.meta["name"] == name}
