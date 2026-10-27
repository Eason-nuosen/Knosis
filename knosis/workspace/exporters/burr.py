"""Burr: relational database -> ontology mapping. The agent gets only SQL (DDL and instance data) and CSV; mapping.json / mappings/ / *.ttl stay in the raw directory."""

from __future__ import annotations

from pathlib import Path

from . import place, register, render, split


@register("burr")
def export(ds, ws: Path, write_data=True, dev=None, seed=0, **opts) -> dict:
    """A single scenario is one task with no dev; `micro` / `micro/<category>` gives one task per scenario, `dev` defaults to about 1/4 (at least 1)."""
    if write_data:
        for key, path in ds.files.items():
            place(path, Path(ws) / "data" / key)
    group = len(ds.tasks) > 1
    tasks = []
    for task in ds.tasks:
        prefix = task.id.removeprefix("burr/") + "/" if group else ""
        tasks.append({"id": task.id, "files": [f"data/{k}" for k in ds.files if k.startswith(prefix)]})
    dev_tasks, tests = split(tasks, (max(1, len(tasks) // 4) if group else 0) if dev is None else dev, seed=seed)
    return {
        "brief": render("burr.md", scenario=ds.scenario, n_dev=len(dev_tasks), n_test=len(tests),
                        layout="每个场景一个子目录 `data/<场景>/`" if group else "所有文件直接在 `data/` 下"),
        "tasks": tests, "dev": dev_tasks, "holdout": [], "output": "predictions.jsonl", "modalities": ["tables"],
    }
