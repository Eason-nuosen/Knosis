"""TabArena: 51 curated single-table datasets (OpenML suite 457), the main leaderboard for tabular foundation models such as TabPFN-2.5.

`knosis download tabarena` exports each OpenML task to local files:

    data/tabarena/<dataset name>/{data.parquet, splits.parquet, meta.json}

splits.parquet holds the official repeat × fold splits (columns: repeat, fold, row, split).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..dataset import Dataset, Task, data_dir, read
from . import register

METRICS = {
    "roc_auc": "binary ROC-AUC",
    "log_loss": "multiclass log loss (lower is better)",
    "rmse": "regression RMSE (lower is better)",
    "elo": "Elo aggregated across datasets (as on the TabArena leaderboard)",
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
