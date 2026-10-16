"""TabArena：单表预测。"""

from __future__ import annotations

from pathlib import Path

from . import register, render, split


@register("tabarena")
def export(ds, ws: Path, repeat=0, fold=0, dev=0, seed=0, write_data=True, **opts) -> dict:
    """`dev`：从训练行里留出多少行（去掉标签）作为反馈用的开发集。"""
    task = next(t for t in ds.tasks if t.meta["repeat"] == repeat and t.meta["fold"] == fold)
    data = ds.read("data")
    target = ds.schema["target"]
    dev_rows, train_rows = split(task.meta["train"], dev, seed=seed)
    frames = {"train": data.iloc[train_rows].copy(), "dev_features": data.iloc[dev_rows].drop(columns=target),
              "test_features": data.iloc[task.meta["test"]].drop(columns=target)}
    for (name, frame), rows in zip(frames.items(), (train_rows, dev_rows, task.meta["test"])):
        frame.insert(0, "row_id", rows)
    if write_data:
        (Path(ws) / "data").mkdir(parents=True, exist_ok=True)
        for name, frame in frames.items():
            if len(frame) or name != "dev_features":
                frame.to_parquet(Path(ws) / f"data/{name}.parquet", index=False)
    categorical = ds.schema["categorical"]
    columns = "\n".join(
        f"- `{name}`: {dtype}" + ("（类别）" if name in categorical else "")
        + (" ← 目标" if name == target else "")
        for name, dtype in data.dtypes.items()
    )
    return {
        "brief": render(
            "tabarena.md", name=ds.scenario, target=target, problem_type=ds.schema["problem_type"],
            n_train=len(train_rows), n_test=len(task.meta["test"]), n_features=len(data.columns) - 1,
            columns=columns, description=ds.schema.get("description", "")[:3000],
        ),
        "tasks": [{"id": row} for row in task.meta["test"]], "dev": [{"id": row} for row in dev_rows],
        "holdout": [], "output": "predictions.csv", "modalities": ["table"],
    }
