"""RelBench scoring: binary classification AUROC, regression MAE, recommendation MAP@k; reference is a trivial baseline on the training set."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from ..data.loaders.relbench import task_splits
from ..knowledge import ontology, ontology_docs
from . import register, register_knowledge
from .bibench import pairs, score_pairs
from .tabular import roc_auc


def average_precision(pred: list, gold: list, k: int) -> float:
    gold, hits, total = set(gold), 0, 0.0
    for i, p in enumerate(pred[:k]):
        if p in gold:
            hits += 1
            total += hits / (i + 1)
    return total / min(k, len(gold)) if gold else 0.0


def as_list(value) -> list:
    return list(value) if isinstance(value, (list, np.ndarray)) else json.loads(value)


@register("relbench")
def score(ws, state, ds, path, ids) -> dict:
    splits = task_splits(ds, state["options"].get("task"))
    spec = splits["test"].meta
    target = spec["target_col"]
    labels = {s: pd.read_parquet(splits[s].answer)[target] for s in ("train", "val", "test")}
    gold = [labels[i.split("-")[0]].iloc[int(i.split("-")[1])] for i in ids]  # row_id looks like val-3 / test-12
    pred = pd.read_csv(path).set_index("row_id")["prediction"].reindex(ids)
    train = labels["train"]
    kind = spec["task_type"]
    if kind == "binary_classification":
        y, p = np.asarray(gold, bool), pred.astype(float).fillna(0).to_numpy()
        metrics = {"roc_auc": roc_auc(y, p) if 0 < y.sum() < len(y) else None}
        items = [{"id": i, "ok": bool((s >= 0.5) == g), "score": float(s), "gold": int(g)} for i, s, g in zip(ids, p, y)]
        reference = {"train_rate": {"roc_auc": 0.5, "positive_rate": float(train.mean())}}
    elif kind == "regression":
        y, p = np.asarray(gold, float), pred.astype(float).to_numpy()
        metrics = {"mae": float(np.nanmean(np.abs(p - y)))}
        items = [{"id": i, "error": float(a - b), "gold": float(b)} for i, a, b in zip(ids, p, y)]
        reference = {"train_mean": {"mae": float(np.mean(np.abs(train.mean() - y)))},
                     "train_median": {"mae": float(np.mean(np.abs(train.median() - y)))}}
    else:
        k = spec.get("eval_k", 10)
        golds = [as_list(g) for g in gold]
        preds = [as_list(p) if isinstance(p, str) else [] for p in pred]
        aps = [average_precision(p, g, k) for p, g in zip(preds, golds)]
        metrics = {f"map@{k}": float(np.mean(aps))}
        items = [{"id": i, "ok": ap > 0, "ap": ap, "gold": [int(x) for x in g][:50]} for i, ap, g in zip(ids, aps, golds)]
        popular = [x for x, _ in Counter(x for g in train for x in g).most_common(k)]
        reference = {"train_popular": {f"map@{k}": float(np.mean([average_precision(popular, g, k) for g in golds]))}}
    return {"metrics": {"task": spec["name"], "task_type": kind, **metrics}, "items": items, "reference": reference}


# ---------------------------------------------------------------- ontology (join discovery) scoring


def gold_pairs(ds) -> set[frozenset]:
    """Manifest foreign keys -> undirected join set: foreign key (table, column) to (primary table, primary key column)."""
    tables = ds.schema["tables"]
    return {frozenset({(ontology.snake(table), column), (ontology.snake(target), tables[target]["pkey"])})
            for table, spec in tables.items()
            for column, target in (spec.get("fkeys") or {}).items() if tables[target].get("pkey")}


def db_report(knowledge, ds) -> dict:
    """All ontologies in the knowledge layer -> join discovery score for this database; reported=False when there is no ontology."""
    docs = {n: d for n, d in ontology_docs(knowledge).items() if "semantic_model" in d}
    if not docs:
        return {"reported": False}
    gold = gold_pairs(ds)
    scores = {name: score_pairs(pairs(d["semantic_model"]), gold) for name, d in docs.items()}
    return {"reported": True, "db": ds.scenario, "units": len(docs), "scores": scores,
            "mean": {k: float(np.mean([s[k] for s in scores.values()])) for k in ("precision", "recall", "f1")}}


@register_knowledge("relbench")
def score_knowledge(ws, state, ds) -> dict:
    ws = Path(ws)
    result = {"ontology": db_report(ws, ds)}
    inherited = ws / "stages/0_inherit"
    if (inherited / "kb").is_dir():
        result["K_inherit"] = db_report(inherited, ds)
    return result
