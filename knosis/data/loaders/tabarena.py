"""TabArena：51 个精选单表数据集（OpenML suite 457），TabPFN-2.5 等表格基础模型的主榜单。

`knosis download tabarena` 把每个 OpenML task 导出成本地文件：

    data/tabarena/<数据集名>/{data.parquet, splits.parquet, meta.json}

splits.parquet 是官方的 repeat × fold 划分（列：repeat, fold, row, split）。
"""

from __future__ import annotations

import json
from pathlib import Path

from ..dataset import Dataset, Task, data_dir, read
from . import register

METRICS = {
    "roc_auc": "二分类 ROC-AUC",
    "log_loss": "多分类 log loss（越低越好）",
    "rmse": "回归 RMSE（越低越好）",
    "elo": "跨数据集聚合的 Elo（TabArena 排行榜口径）",
}


def scenarios(root: str | Path | None = None) -> list[str]:
    base = Path(root or data_dir("tabarena"))
    return sorted(p.parent.name for p in base.glob("*/meta.json"))


@register("tabarena", scenarios=scenarios)
def load(scenario: str, root: str | Path | None = None) -> Dataset:
    ddir = Path(root or data_dir("tabarena")) / scenario
    meta = json.loads((ddir / "meta.json").read_text())
    files = {"data": ddir / "data.parquet", "splits": ddir / "splits.parquet"}

    y = read(files["data"])[meta["target"]]
    tasks = []
    for (r, f), g in read(files["splits"]).groupby(["repeat", "fold"]):
        train = g.loc[g["split"] == "train", "row"].tolist()
        test = g.loc[g["split"] == "test", "row"].tolist()
        tasks.append(Task(
            id=f"{scenario}/r{r}f{f}",
            input=f"Predict `{meta['target']}` ({meta['problem_type']}) for the test rows.",
            answer=y.iloc[test].tolist(),
            kind=meta["problem_type"],
            meta={"repeat": int(r), "fold": int(f), "train": train, "test": test},
        ))

    schema = {k: meta[k] for k in ("target", "problem_type", "categorical", "n_rows", "n_features")}
    schema["description"] = meta.get("description", "")
    return Dataset("tabarena", scenario, ddir, files=files, schema=schema, tasks=tasks, metrics=METRICS)
