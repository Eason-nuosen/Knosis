"""NewtonBench 打分：调用上游 `evaluate_law`（5000 个采样点上的 RMSLE，采样照上游），关闭 LLM 符号裁判。

ok 取 RMSLE ≤ 0.01，是 Knosis 的约定（上游的成功标准是符号等价）。
"""

from __future__ import annotations

import numpy as np

from ..data.loaders.newtonbench import upstream
from . import answers, register

OK_RMSLE = 0.01


@register("newtonbench")
def score(ws, state, ds, path, ids) -> dict:
    from modules.common.evaluation import extract_formula_from_function

    module = upstream(ds.scenario, ds.root.parents[1])
    laws = __import__(f"modules.{ds.scenario}.laws", fromlist=["get_ground_truth_law"])
    predictions = answers(path)
    tasks = {t.id: t for t in ds.tasks}
    items = []
    for tid in ids:
        meta = tasks[tid].meta
        np.random.seed(0)  # 上游每次随机采样测试点；固定种子使分数可复现
        result = module.evaluate_law(predictions.get(tid, ""), module.PARAM_DESCRIPTION, meta["difficulty"], meta["version"])
        gold = extract_formula_from_function(laws.get_ground_truth_law(meta["difficulty"], meta["version"])[0])
        rmsle = result["rmsle"]
        items.append({"id": tid, "ok": bool(rmsle <= OK_RMSLE), "rmsle": rmsle, "error": result["error"], "gold": gold})
    rmsle = np.array([i["rmsle"] for i in items], dtype=float)
    return {"metrics": {"ok_rate": float(np.mean([i["ok"] for i in items])) if items else 0.0,
                        "rmsle_median": float(np.nanmedian(rmsle)) if np.isfinite(rmsle).any() else float("nan"),
                        "invalid": int(np.isnan(rmsle).sum()), "missing": sum(tid not in predictions for tid in ids),
                        "symbolic_accuracy": "未实现（需要 LLM 裁判）"},
            "items": items, "reference": {}}
