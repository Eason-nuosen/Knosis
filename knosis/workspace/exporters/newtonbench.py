"""NewtonBench: discover (modified) physical laws through experiments. There are no data files; the GT law stays in the raw directory,
and the agent runs experiments via the `newton` tool. The three experiment systems of the same difficulty and version share one law,
so dev and test are split by whole (difficulty, version) groups and dev feedback cannot leak a test law."""

from __future__ import annotations

from pathlib import Path

from ...data.loaders.newtonbench import upstream
from . import register, render, split


@register("newtonbench")
def export(ds, ws: Path, write_data=True, dev=2, limit=None, seed=0, noise=0.0, systems=None, **opts) -> dict:
    """`dev`: number of (difficulty, version) groups for feedback; `limit`: number of test groups; `noise`: relative noise level of observations (upstream default 0);
    `systems`: use only these experiment systems (comma-separated, e.g. `vanilla_equation`); all three by default."""
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
