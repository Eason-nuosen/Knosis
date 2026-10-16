"""NGDBench：含噪观测属性图 + 图问答。"""

from __future__ import annotations

import pickle
from collections import Counter
from pathlib import Path

from . import register, render, split


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


@register("ngdbench")
def export(ds, ws: Path, write_data=True, dev=50, limit=None, seed=0, **opts) -> dict:
    """`dev`：用于反馈的开发题数；`limit`：抽样的测试题数（NGD-Fin 全量约 8700 题）。"""
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
    dev_tasks, tests = split([task for i, task in enumerate(tasks) if i not in indices], dev, limit, seed)
    return {
        "brief": render(
            f"ngdbench-{ds.scenario}.md", **graph_summary(graph),
            examples="\n".join(f"- [{t['kind']}] {t['question']}" for t in examples),
        ),
        "tasks": tests, "dev": dev_tasks, "holdout": [task["id"] for task in examples],
        "output": "predictions.jsonl", "modalities": ["graph"],
    }
