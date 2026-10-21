"""NewtonBench：通过实验发现（被改写过的）物理定律。没有数据文件，GT 定律留在原始目录，
agent 通过 `newton` 工具做实验。同一难度、同一版本的三种实验系统共用一条定律，
所以 dev 与测试按（难度, 版本）整组切分，dev 反馈不会泄漏测试题的定律。"""

from __future__ import annotations

from pathlib import Path

from ...data.loaders.newtonbench import upstream
from . import register, render, split


@register("newtonbench")
def export(ds, ws: Path, write_data=True, dev=2, limit=None, seed=0, noise=0.0, systems=None, **opts) -> dict:
    """`dev`：用于反馈的（难度, 版本）组数；`limit`：测试组数；`noise`：实验观测的相对噪声水平（上游默认 0）；
    `systems`：只用这些实验系统（逗号分隔，如 `vanilla_equation`），默认三种都用。"""
    keep = set(systems.split(",")) if systems else None
    module = upstream(ds.scenario, ds.root.parents[1])
    groups = {}
    for t in ds.tasks:
        if keep and t.meta["complexity"] not in keep:
            continue
        groups.setdefault((t.meta["difficulty"], t.meta["version"]), []).append(
            {"id": t.id, "difficulty": t.meta["difficulty"], "version": t.meta["version"],
             "system": t.meta["complexity"], "signature": module.FUNCTION_SIGNATURE})
    dev_groups, test_groups = split(list(groups.values()), dev, limit, seed)
    systems = sorted({t.meta["complexity"] for t in ds.tasks if not keep or t.meta["complexity"] in keep})
    apparatus = "\n\n".join(f"### {s}\n\n{module.get_task_prompt(s, False, noise)}" for s in systems)
    return {
        "brief": render("newtonbench.md", domain=ds.scenario, n_tasks=sum(map(len, groups.values())), params=module.PARAM_DESCRIPTION,
                        signature=module.FUNCTION_SIGNATURE, systems=", ".join(systems), apparatus=apparatus),
        "tasks": [t for g in test_groups for t in g], "dev": [t for g in dev_groups for t in g],
        "holdout": [], "output": "predictions.jsonl", "modalities": ["simulator"],
    }
