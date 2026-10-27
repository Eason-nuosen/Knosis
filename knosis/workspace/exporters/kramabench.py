"""KramaBench: data lake -> insight. The agent gets only the data lake and questions; answers, reference solutions and subtasks stay in the raw directory."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ...lang import t
from . import place, register, render, split

# Upstream answer_type minus exact / approximate is shown to the agent; it only describes the answer's shape.
def kinds() -> dict:
    return {"numeric": t("numeric", "数值"), "string": t("string", "字符串"), "list": t("list", "列表")}


@register("kramabench")
def export(ds, ws: Path, write_data=True, dev=None, seed=0, **opts) -> dict:
    """`dev`: number of dev tasks, about 1/4 by default (at least 1)."""
    lake = ds.files["lake"]
    files = sorted(p for p in lake.rglob("*") if p.is_file())
    if write_data:
        for p in files:
            place(p, Path(ws) / "data" / p.relative_to(lake))
    tasks = [{"id": t.id, "question": t.input, "answer_kind": kinds()[t.kind.split("_")[0]]} for t in ds.tasks]
    dev_tasks, tests = split(tasks, max(1, len(tasks) // 4) if dev is None else dev, seed=seed)
    suffixes = Counter(p.suffix.lower() or t("(no suffix)", "(无后缀)") for p in files)
    return {
        "brief": render(
            "kramabench.md", domain=ds.scenario, n_files=len(files),
            size_mb=f"{sum(p.stat().st_size for p in files) / 2**20:.0f}",
            suffixes=t(", ", "、").join(f"{s} {n}" for s, n in suffixes.most_common()),
            n_dev=len(dev_tasks), n_test=len(tests),
        ),
        "tasks": tests, "dev": dev_tasks, "holdout": [], "output": "predictions.jsonl", "modalities": ["table", "tables"],
    }
