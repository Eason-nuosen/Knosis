"""BI-Bench：真实 Power BI 项目的多表业务问答。scenario 为用例 id，或 `all`（100 个用例一起）。"""

from __future__ import annotations

from pathlib import Path

from ...data import load_dataset
from ...knowledge import ontology
from . import place, register, render, split


def merged_ontology(ds) -> dict:
    """各用例的 core 层合成一份：dataset 名前加用例前缀，避免不同用例的同名表冲突。"""
    datasets, relationships = [], []
    for task in ds.tasks:
        model = ontology.from_bibench(load_dataset("bibench", task.id, root=ds.root.parent))
        prefix = f"c{ontology.snake(task.id)}_"
        for d in model["datasets"]:
            datasets.append({**d, "name": prefix + d["name"], "source": f"{task.id}/{d['source']}"})
        for r in model.get("relationships", []):
            relationships.append({**r, "name": prefix + r["name"], "from": prefix + r["from"], "to": prefix + r["to"]})
    return ontology.semantic_model("bibench_all", datasets, relationships,
                                   provenance={"method": "converted", "author": "knosis.from_bibench"},
                                   source={"dataset": "bi-bench", "item": "all"})


@register("bibench")
def export(ds, ws: Path, write_data=True, dev=None, limit=None, seed=0, metadata=False, **opts) -> dict:
    """`dev` 默认：all 模式 20 个用例，项目模式（scenario 是项目 id）1 个，单用例 0。
    `metadata=true` 时把 Power BI 模型元数据转成本体放进初始知识层。"""
    ws = Path(ws)
    single = len(ds.tasks) == 1
    tasks = [{"id": t.id, "question": t.input, "tables": f"data/{t.id}/"} for t in ds.tasks]
    default = 0 if single else 20 if ds.scenario == "all" else 1
    dev_tasks, tests = split(tasks, default if dev is None else dev, limit, seed)
    lines = []
    for task in ds.tasks:
        csvs = sorted(Path(task.meta["dir"]).glob("*.csv"))  # 只放表；oracle、transformation/、join/ 都是提示，不导出
        if write_data:
            for f in csvs:
                place(f, ws / "data" / task.id / f.name)
        lines.append(f"- `data/{task.id}/`：{len(csvs)} 张表（{', '.join(f.stem for f in csvs[:8])}{' …' if len(csvs) > 8 else ''}）")
    if write_data and metadata:
        model = ontology.from_bibench(ds) if single else merged_ontology(ds)
        ontology.write_ontology(ws / "kb/knowledge/ontology", {"semantic_model": model})
    brief = render(
        "bibench.md", n_cases=len(ds.tasks), cases="\n".join(lines), n_dev=len(dev_tasks), n_test=len(tests),
        metadata=("`kb/knowledge/ontology/` 里已有一份由原 Power BI 项目模型元数据转换来的本体 core 层"
                  "（表、列、计算列的 DAX、项目作者定义的表间关系），可以采用、修订或撤回。")
        if metadata else "没有提供原 BI 项目的模型元数据（表间关系等），需要自己从数据里判断。",
    )
    return {"brief": brief, "tasks": tests, "dev": dev_tasks, "holdout": [],
            "output": "predictions.jsonl", "modalities": ["tables"]}
