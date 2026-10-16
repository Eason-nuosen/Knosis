"""LLM-SRBench 打分：NMSE（与上游 `compute_output_base_metrics` 相同，忽略 NaN 预测点）与 Acc_τ。

Acc_τ 按论文定义：所有测试点的最大相对误差 ≤ τ 记为 1（上游代码未给出实现）。
符号等价需要 LLM 裁判，不做。
"""

from __future__ import annotations

import h5py
import numpy as np

from . import answers, register

TAU = 0.1


def predict(expression: str, symbols, samples: np.ndarray) -> np.ndarray:
    scope = {"np": np, **{s: samples[:, i + 1] for i, s in enumerate(symbols[1:])}}
    with np.errstate(all="ignore"):
        return np.broadcast_to(np.asarray(eval(expression, scope), dtype=float), samples[:, 0].shape)


def metrics(expression, symbols, samples) -> dict:
    y = samples[:, 0].astype(float)
    try:
        pred = predict(expression, symbols, samples)
    except Exception as error:  # 交付的表达式本身写错是正常结果，记为无效而不是让评测崩掉
        return {"nmse": float("inf"), "acc": False, "error": f"{type(error).__name__}: {error}"}
    valid = ~np.isnan(pred)
    nmse = float(np.mean((y[valid] - pred[valid]) ** 2) / np.var(y[valid])) if valid.any() else float("inf")
    with np.errstate(all="ignore"):
        acc = bool(valid.all() and np.max(np.abs(pred - y) / np.abs(y)) <= TAU)
    return {"nmse": nmse, "acc": acc}


@register("llm-srbench")
def score(ws, state, ds, path, ids) -> dict:
    tasks = {t.id: t for t in ds.tasks}
    predictions = answers(path)
    items = []
    with h5py.File(ds.files["hdf5"], "r") as h5:
        for tid in ids:
            task = tasks[tid]
            group = h5[task.meta["hdf5_group"]]
            expression = predictions.get(tid) or "np.nan"
            test = metrics(expression, task.meta["symbols"], group["test"][:])
            item = {"id": tid, "ok": test["acc"], "nmse": test["nmse"], "gold": task.answer}
            if "error" in test:
                item["error"] = test["error"]
            if "ood_test" in group:
                ood = metrics(expression, task.meta["symbols"], group["ood_test"][:])
                item |= {"ood_nmse": ood["nmse"], "ood_ok": ood["acc"]}
            items.append(item)
    nmse = np.array([i["nmse"] for i in items])
    result = {"acc_0.1": float(np.mean([i["ok"] for i in items])) if items else 0.0,
              "nmse_median": float(np.median(nmse)) if items else float("inf"),
              "missing": sum(tid not in predictions for tid in ids),
              "symbolic_accuracy": "未实现（需要 LLM 裁判）"}
    ood = [i for i in items if "ood_nmse" in i]
    if ood:
        result |= {"ood_acc_0.1": float(np.mean([i["ood_ok"] for i in ood])),
                   "ood_nmse_median": float(np.median([i["ood_nmse"] for i in ood]))}
    return {"metrics": result, "items": items, "reference": {}}
