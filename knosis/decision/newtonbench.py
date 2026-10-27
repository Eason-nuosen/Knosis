"""NewtonBench scoring: calls upstream `evaluate_law` (RMSLE over 5000 sampled points, sampled as upstream), with the LLM symbolic judge disabled.

ok means RMSLE ≤ 0.01, a Knosis convention (upstream's success criterion is symbolic equivalence).
"""

from __future__ import annotations

import numpy as np

from ..data.loaders.newtonbench import upstream
from . import answers, register

OK_RMSLE = 0.01


@register("newtonbench")
def score(ws, state, ds, path, ids) -> dict:
    module = upstream(ds.scenario, ds.root.parents[1])  # puts the upstream root on sys.path, then imports its modules package
    from modules.common.evaluation import extract_formula_from_function

    laws = __import__(f"modules.{ds.scenario}.laws", fromlist=["get_ground_truth_law"])
    predictions = answers(path)
    tasks = {t.id: t for t in ds.tasks}
    items = []
    for tid in ids:
        meta = tasks[tid].meta
        np.random.seed(0)  # upstream samples test points randomly each time; fix the seed for reproducible scores
        result = module.evaluate_law(predictions.get(tid, ""), module.PARAM_DESCRIPTION, meta["difficulty"], meta["version"])
        gold = extract_formula_from_function(laws.get_ground_truth_law(meta["difficulty"], meta["version"])[0])
        rmsle = result["rmsle"]
        items.append({"id": tid, "ok": bool(rmsle <= OK_RMSLE), "rmsle": rmsle, "error": result["error"], "gold": gold})
    rmsle = np.array([i["rmsle"] for i in items], dtype=float)
    return {"metrics": {"ok_rate": float(np.mean([i["ok"] for i in items])) if items else 0.0,
                        "rmsle_median": float(np.nanmedian(rmsle)) if np.isfinite(rmsle).any() else float("nan"),
                        "invalid": int(np.isnan(rmsle).sum()), "missing": sum(tid not in predictions for tid in ids),
                        "symbolic_accuracy": "not implemented (needs an LLM judge)"},
            "items": items, "reference": {}}
