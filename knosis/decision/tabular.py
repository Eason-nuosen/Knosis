"""单表预测（TabArena）打分：回归 RMSE / MAE / R²；分类 accuracy，给了概率时加 ROC-AUC / log loss。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..knowledge import active, load_units
from ..knowledge.evidence import run_check
from . import register, register_knowledge


def roc_auc(truth: np.ndarray, score: np.ndarray) -> float:
    ranks = pd.Series(score).rank().to_numpy()
    pos = truth.sum()
    return float((ranks[truth].sum() - pos * (pos + 1) / 2) / (pos * (len(truth) - pos)))


def regression(y, pred) -> dict:
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    err = pred - y
    return {"rmse": float(np.sqrt(np.mean(err ** 2))), "mae": float(np.mean(np.abs(err))),
            "r2": float(1 - np.sum(err ** 2) / np.sum((y - y.mean()) ** 2))}


def classification(y, predictions: pd.DataFrame, labels) -> dict:
    y = np.asarray([str(v) for v in y])
    result = {"accuracy": float(np.mean(predictions["prediction"].astype(str).to_numpy() == y))}
    columns = {label: f"probability_{label}" for label in labels}
    if all(c in predictions for c in columns.values()):
        probs = predictions[list(columns.values())].to_numpy(float)
        probs = np.clip(probs / probs.sum(axis=1, keepdims=True), 1e-15, 1)
        index = {label: i for i, label in enumerate(columns)}
        result["log_loss"] = float(-np.mean(np.log(probs[np.arange(len(y)), [index[v] for v in y]])))
        if len(labels) == 2 and len(set(y)) == 2:
            result["roc_auc"] = roc_auc(y == labels[1], probs[:, 1])
    return result


def score_rows(truth: pd.Series, predictions: pd.DataFrame, train_y: pd.Series, problem_type: str) -> dict:
    """`truth` 与 `predictions` 按行 id 对齐；RelBench 等其他表格任务也复用。"""
    predictions = predictions.loc[truth.index]
    if problem_type == "regression":
        metrics = regression(truth, predictions["prediction"])
        reference = regression(truth, np.full(len(truth), train_y.mean()))
        items = [{"id": i, "error": float(p - g), "gold": g} for i, p, g in
                 zip(truth.index.tolist(), predictions["prediction"].astype(float), truth.tolist())]
    else:
        labels = sorted(str(v) for v in train_y.dropna().unique())
        metrics = classification(truth, predictions, labels)
        reference = classification(truth, pd.DataFrame({"prediction": [train_y.mode()[0]] * len(truth)}), labels)
        items = [{"id": i, "ok": str(p) == str(g), "gold": g} for i, p, g in
                 zip(truth.index.tolist(), predictions["prediction"], truth.tolist())]
    return {"metrics": {"problem_type": problem_type, **metrics}, "items": items, "reference": {"train_prior": reference}}


@register("tabarena")
def score(ws, state, ds, path, ids) -> dict:
    opts = state["options"]
    task = next(t for t in ds.tasks if t.meta["repeat"] == opts.get("repeat", 0) and t.meta["fold"] == opts.get("fold", 0))
    y = ds.read("data")[ds.schema["target"]]
    truth = pd.Series(y.iloc[ids].tolist(), index=ids)  # row_id 就是原始行号
    predictions = pd.read_csv(path).set_index("row_id")
    return score_rows(truth, predictions, y.iloc[task.meta["train"]], ds.schema["problem_type"])


@register_knowledge("tabarena")
def score_knowledge(ws, state, ds) -> dict:
    """带 SQL 检查的活跃单元，在训练行与带标签的留出（测试）行上各跑一次：规律是否在没见过的数据上仍成立。"""
    opts = state["options"]
    task = next(t for t in ds.tasks if t.meta["repeat"] == opts.get("repeat", 0) and t.meta["fold"] == opts.get("fold", 0))
    data = ds.read("data")
    frames = {name: data.iloc[task.meta[name]].assign(row_id=lambda f: f.index).reset_index(drop=True)
              for name in ("train", "test")}
    frames = {k: f[["row_id", *[c for c in f.columns if c != "row_id"]]] for k, f in frames.items()}
    items = []
    for unit in active(load_units(ws / "knowledge/units.jsonl")):
        if unit.get("check", {}).get("kind") != "sql":
            continue
        train, _ = run_check(unit, ws, {"train": frames["train"]})
        held, note = run_check(unit, ws, {"train": frames["test"]})
        items.append({"id": unit["id"], "status": unit["status"], "train": train, "heldout": held, "note": note[:200]})
    holds = [i for i in items if i["train"] == "support"]
    return {"checks": len(items), "support_on_train": len(holds),
            "heldout_support_rate": sum(i["heldout"] == "support" for i in holds) / len(holds) if holds else None,
            "items": items}
