"""导出器：把一个数据集变成工作区里 agent 可见的部分（数据 + BRIEF + 题目）；GT 留在原始数据目录。

新增数据集的工作区支持：写一个 `export_<name>(ds, ws, write_data=True, **opts) -> dict`，
返回 brief / tasks / holdout / output / modalities，并登记到 `EXPORTERS`。
"""

from __future__ import annotations

import pickle
import random
from collections import Counter
from pathlib import Path
from string import Template

BRIEFS = Path(__file__).parent / "templates" / "briefs"


def render(template, **values):
    return Template((BRIEFS / template).read_text(encoding="utf-8")).substitute(values)


def graph_summary(graph):
    nodes = Counter(attrs.get("label", "(无 label)") for _, attrs in graph.nodes(data=True))
    edges = Counter(attrs.get("label", "(无 label)") for *_, attrs in graph.edges(data=True))
    attributes = {}
    for _, attrs in graph.nodes(data=True):
        attributes.setdefault(attrs.get("label", "(无 label)"), set()).update(attrs)
    return {
        "graph_type": type(graph).__name__, "n_nodes": graph.number_of_nodes(),
        "n_edges": graph.number_of_edges(),
        "node_types": "\n".join(f"- {label}: {n}" for label, n in sorted(nodes.items())),
        "edge_types": "\n".join(f"- {label}: {n}" for label, n in sorted(edges.items())),
        "attributes": "\n".join(
            f"- {label}: {', '.join(sorted(keys - {'label'}))}" for label, keys in sorted(attributes.items())
        ),
    }


def export_ngdbench(ds, ws: Path, write_data=True, limit=None, seed=0, **opts) -> dict:
    """`limit`：测试题按 `seed` 抽样的数量（NGD-Fin 全量约 8700 题）。"""
    ws = Path(ws)
    clean = ds.read("clean")
    graph = ds.read("perturbed") if "perturbed" in ds.files else clean.copy()
    node_keys = {key for _, attrs in clean.nodes(data=True) for key in attrs}
    edge_keys = {key for *_, attrs in clean.edges(data=True) for key in attrs}
    # 属性键白名单来自 clean 图；加噪痕迹（is_noise / noise_similarity / original_name 等）会直接泄漏去噪答案。
    graph.graph.clear()
    for _, attrs in graph.nodes(data=True):
        for key in set(attrs) - node_keys:
            del attrs[key]
    for *_, attrs in graph.edges(data=True):
        for key in set(attrs) - edge_keys:
            del attrs[key]
    if write_data:
        (ws / "data").mkdir(parents=True, exist_ok=True)
        with (ws / "data/graph.gpickle").open("wb") as fh:
            pickle.dump(graph, fh)
    tasks = [
        {"id": task.id, "kind": task.kind, "question": task.meta.get("nlp") or task.input,
         "cypher": task.meta.get("query", "")}
        for task in ds.tasks if task.kind.startswith(("complex_query", "query_results"))
    ]
    n_examples = min(6, len(tasks))
    indices = {i * (len(tasks) - 1) // max(1, n_examples - 1) for i in range(n_examples)}
    examples = [task for i, task in enumerate(tasks) if i in indices]
    tests = [task for i, task in enumerate(tasks) if i not in indices]
    if limit is not None and limit < len(tests):
        tests = sorted(random.Random(seed).sample(tests, limit), key=lambda t: t["id"])
    return {
        "brief": render(
            f"ngdbench-{ds.scenario}.md", **graph_summary(graph),
            examples="\n".join(f"- [{t['kind']}] {t['question']}" for t in examples),
        ),
        "tasks": tests, "holdout": [task["id"] for task in examples],
        "output": "predictions.jsonl", "modalities": ["graph"],
    }


def export_tabarena(ds, ws: Path, repeat=0, fold=0, write_data=True, **opts) -> dict:
    task = next(t for t in ds.tasks if t.meta["repeat"] == repeat and t.meta["fold"] == fold)
    data = ds.read("data")
    target = ds.schema["target"]
    train = data.iloc[task.meta["train"]].copy()
    test = data.iloc[task.meta["test"]].drop(columns=target).copy()
    train.insert(0, "row_id", task.meta["train"])
    test.insert(0, "row_id", task.meta["test"])
    if write_data:
        (Path(ws) / "data").mkdir(parents=True, exist_ok=True)
        train.to_parquet(Path(ws) / "data/train.parquet", index=False)
        test.to_parquet(Path(ws) / "data/test_features.parquet", index=False)
    categorical = ds.schema["categorical"]
    columns = "\n".join(
        f"- `{name}`: {dtype}" + ("（类别）" if name in categorical else "")
        + (" ← 目标" if name == target else "")
        for name, dtype in data.dtypes.items()
    )
    return {
        "brief": render(
            "tabarena.md", name=ds.scenario, target=target, problem_type=ds.schema["problem_type"],
            n_train=len(train), n_test=len(test), n_features=len(data.columns) - 1,
            columns=columns, description=ds.schema.get("description", "")[:3000],
        ),
        "tasks": [{"id": task.id, "kind": task.kind,
                   "question": f"为 data/test_features.parquet 的每一行预测 `{target}`。"}],
        "holdout": [], "output": "predictions.csv", "modalities": ["table"],
    }


EXPORTERS = {"ngdbench": export_ngdbench, "tabarena": export_tabarena}
