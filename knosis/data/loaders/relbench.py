"""RelBench：关系数据库上的实体级预测任务，按时间切分。

    data/relbench/<db>/{manifest.yaml, db/<table>.parquet, tasks/<task>/{manifest.yaml,train,val,test}.parquet}
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..dataset import Dataset, Task, data_dir
from . import register

DBS = ("rel-amazon", "rel-avito", "rel-event", "rel-f1", "rel-hm", "rel-stack", "rel-trial")

METRICS = {
    "roc_auc": "二分类 AUROC",
    "map": "推荐任务 MAP",
    "nmae": "回归任务归一化 MAE（越低越好）",
    "delta_with_knowledge": "接入 Knosis 知识前后的指标差",
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
    """一个任务的 {train / val / test: Task}；`task` 不给就用第一个任务。Task.answer 是该划分的标签表路径。"""
    name = task or ds.tasks[0].meta["name"]
    return {t.split: t for t in ds.tasks if t.meta["name"] == name}
