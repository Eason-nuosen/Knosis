"""LLM-SRBench：符号回归。每题只导出训练数据，真值表达式、test、ood_test 都留在原始 HDF5。"""

from __future__ import annotations

from pathlib import Path

import h5py
import pandas as pd

from . import register, render, split


@register("llm-srbench")
def export(ds, ws: Path, write_data=True, dev=None, limit=None, seed=0, **opts) -> dict:
    """`dev`：用于反馈的题数，默认约 20%；`limit`：抽样的测试题数。"""
    tasks = [{"id": t.id, "name": t.meta["name"], "output": t.meta["symbols"][0], "inputs": t.meta["symbols"][1:],
              "descriptions": dict(zip(t.meta["symbols"], t.meta["symbol_descs"])),
              "data": f"data/{t.meta['name']}/train.parquet"} for t in ds.tasks]
    dev_tasks, tests = split(tasks, round(0.2 * len(tasks)) if dev is None else dev, limit, seed)
    if write_data:
        used = {t["id"] for t in dev_tasks + tests}
        with h5py.File(ds.files["hdf5"], "r") as h5:
            for t in ds.tasks:
                if t.id not in used:
                    continue
                path = Path(ws) / f"data/{t.meta['name']}/train.parquet"
                path.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame(h5[t.meta["hdf5_group"]]["train"][:], columns=t.meta["symbols"]).to_parquet(path, index=False)
    example = tasks[0]
    return {
        "brief": render("llm-srbench.md", split=ds.scenario, n_tasks=len(tasks), example_id=example["id"],
                        example_output=example["output"], example_inputs=", ".join(example["inputs"]),
                        example_desc="\n".join(f"- `{k}`: {v}" for k, v in example["descriptions"].items())),
        "tasks": tests, "dev": dev_tasks, "holdout": [], "output": "predictions.jsonl", "modalities": ["table"],
    }
