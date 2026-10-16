"""单表预测（TabArena）打分：回归 RMSE / MAE / R²；分类 accuracy，给了概率时加 ROC-AUC / log loss。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import register


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
        if len(labels) == 2:
            result["roc_auc"] = roc_auc(y == labels[1], probs[:, 1])
    return result


@register("tabarena")
def score(ws, state, ds) -> dict:
    opts = state["options"]
    task = next(t for t in ds.tasks if t.meta["repeat"] == opts.get("repeat", 0) and t.meta["fold"] == opts.get("fold", 0))
    target = ds.schema["target"]
    train_y = ds.read("data")[target].iloc[task.meta["train"]]
    truth = pd.Series(task.answer, index=task.meta["test"])
    predictions = pd.read_csv(ws / "stages/4_decide" / state["output"]).set_index("row_id").loc[truth.index]
    if ds.schema["problem_type"] == "regression":
        metrics = regression(truth, predictions["prediction"])
        reference = regression(truth, np.full(len(truth), train_y.mean()))
    else:
        labels = sorted(str(v) for v in train_y.dropna().unique())
        metrics = classification(truth, predictions, labels)
        majority = pd.DataFrame({"prediction": [train_y.mode()[0]] * len(truth)})
        reference = classification(truth, majority, labels)
    return {"n": len(truth), "problem_type": ds.schema["problem_type"], **metrics,
            "reference": {"train_prior": reference}}
