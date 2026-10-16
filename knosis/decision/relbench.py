"""RelBench 打分：二分类 AUROC、回归 MAE、推荐 MAP@k；参照为训练集上的平凡基线。"""

from __future__ import annotations

import json
from collections import Counter

import numpy as np
import pandas as pd

from ..data.loaders.relbench import task_splits
from . import register
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
    gold = [labels[i.split("-")[0]].iloc[int(i.split("-")[1])] for i in ids]  # row_id 形如 val-3 / test-12
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
