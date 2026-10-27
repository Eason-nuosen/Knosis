"""RelBench: entity-level prediction on relational databases (binary classification / regression / recommendation), split by time."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ...data.loaders.relbench import task_splits
from . import place, register, render, split


def key_columns(spec) -> list[str]:
    """Columns of the test table left for the agent: entity and time."""
    entity = spec.get("entity_col") or spec["src_entity_col"]
    return [spec["time_col"], entity]


def row_ids(prefix, n) -> list[str]:
    return [f"{prefix}-{i}" for i in range(n)]


@register("relbench")
def export(ds, ws: Path, write_data=True, task=None, dev=None, limit=None, seed=0, **opts) -> dict:
    """train keeps labels; val without labels becomes dev (`dev` caps the count); test keeps only entity and time columns (`limit` samples)."""
    splits = task_splits(ds, task)
    spec = splits["test"].meta
    val, test = (pd.read_parquet(splits[s].answer) for s in ("val", "test"))
    dev_ids, _ = split(row_ids("val", len(val)), len(val) if dev is None else dev, seed=seed)
    _, test_ids = split(row_ids("test", len(test)), 0, limit, seed)
    cutoff = pd.Timestamp(ds.schema["test_timestamp"])
    tables = []
    for table, path in ds.files.items():
        time_col = ds.schema["tables"].get(table, {}).get("time_col")
        out = Path(ws) / "data/db" / f"{table}.parquet"
        if time_col:
            # Keep only rows before the test time (RelBench's upto_test_timestamp convention): future rows reveal test labels directly.
            keep = ~(pd.read_parquet(path, columns=[time_col])[time_col] >= cutoff)
            if write_data:
                out.parent.mkdir(parents=True, exist_ok=True)
                pd.read_parquet(path)[keep.to_numpy()].to_parquet(out, index=False)
            n = int(keep.sum())
        else:
            if write_data:
                place(path, out)
            n = pq.ParquetFile(path).metadata.num_rows
        tables.append(f"- `{table}`：{n} 行，列 {', '.join(pq.read_schema(path).names)}")
    if write_data:
        train = pd.read_parquet(splits["train"].answer)
        train.insert(0, "row_id", row_ids("train", len(train)))
        train.to_parquet(Path(ws) / "data/train.parquet", index=False)
        for name, frame, prefix, ids in (("dev_features", val, "val", dev_ids), ("test_features", test, "test", test_ids)):
            frame = frame[key_columns(spec)].copy()
            frame.insert(0, "row_id", row_ids(prefix, len(frame)))
            frame[frame["row_id"].isin(ids)].to_parquet(Path(ws) / f"data/{name}.parquet", index=False)
    schema = "\n".join(
        f"- `{t}`：主键 {s.get('pkey') or '无'}，时间列 {s.get('time_col') or '无'}，外键 {s.get('fkeys') or '无'}"
        for t, s in ds.schema["tables"].items()
    )
    formats = {
        "binary_classification": "`prediction` 为正类（标签 1）的概率或分数；按 AUROC 评测",
        "regression": "`prediction` 为数值；按 MAE 评测",
        "recommendation": f"`prediction` 为 JSON 列表，按相关度从高到低列出最多 {spec.get('eval_k', 10)} 个 "
                          f"`{spec.get('dst_entity_col')}`；按 MAP@{spec.get('eval_k', 10)} 评测",
    }
    brief = render(
        "relbench.md", db=ds.scenario, description=ds.schema.get("description", ""), task=spec["name"],
        task_type=spec["task_type"], task_description=spec.get("description", ""), target=spec["target_col"],
        keys=", ".join(f"`{c}`" for c in key_columns(spec)), cutoff=cutoff.date(),
        val_timestamp=ds.schema["val_timestamp"], tables="\n".join(tables), schema=schema,
        n_dev=len(dev_ids), n_test=len(test_ids), format=formats[spec["task_type"]],
    )
    return {"brief": brief, "tasks": [{"id": i} for i in test_ids], "dev": [{"id": i} for i in dev_ids],
            "holdout": [], "output": "predictions.csv", "modalities": ["table", "tables"]}
