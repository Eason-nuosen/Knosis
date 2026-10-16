"""KramaBench：数据湖 → 洞察。agent 只拿到数据湖与问题；答案、参考解与子任务都留在原始目录。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from . import place, register, render, split

# 上游的 answer_type 去掉 exact / approximate 后告诉 agent，只说明答案的形状。
KINDS = {"numeric": "数值", "string": "字符串", "list": "列表"}


@register("kramabench")
def export(ds, ws: Path, write_data=True, dev=None, seed=0, **opts) -> dict:
    """`dev`：开发题数，默认约 1/4（至少 1 题）。"""
    lake = ds.files["lake"]
    files = sorted(p for p in lake.rglob("*") if p.is_file())
    if write_data:
        for p in files:
            place(p, Path(ws) / "data" / p.relative_to(lake))
    tasks = [{"id": t.id, "question": t.input, "answer_kind": KINDS[t.kind.split("_")[0]]} for t in ds.tasks]
    dev_tasks, tests = split(tasks, max(1, len(tasks) // 4) if dev is None else dev, seed=seed)
    suffixes = Counter(p.suffix.lower() or "(无后缀)" for p in files)
    return {
        "brief": render(
            "kramabench.md", domain=ds.scenario, n_files=len(files),
            size_mb=f"{sum(p.stat().st_size for p in files) / 2**20:.0f}",
            suffixes="、".join(f"{s} {n}" for s, n in suffixes.most_common()),
            n_dev=len(dev_tasks), n_test=len(tests),
        ),
        "tasks": tests, "dev": dev_tasks, "holdout": [], "output": "predictions.jsonl", "modalities": ["table", "tables"],
    }
