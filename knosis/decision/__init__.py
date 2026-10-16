"""决策层：decide 产物如何打分，以及知识在决策中被如何使用。

每个数据集一个打分器 `score(ws, state, ds, path, ids) -> dict`，用 `@register("<数据集>")` 注册：
`path` 是交付文件（格式见导出器的 `output`），`ids` 是要打分的题目 id，`ds` 从原始数据目录重新加载（含 GT）。
返回 `{"metrics": {...}, "items": [{"id", "ok", "gold", ...}], "reference": {...}}`：
`evaluate` 在测试题上调用它；知识层的反馈（`knowledge.feedback.submit`）在 dev 题上调用同一个函数。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from ..data import load_dataset
from ..knowledge import INACTIVE, load_units

SCORERS: dict[str, Callable] = {}


def register(name: str):
    def deco(fn):
        SCORERS[name] = fn
        return fn

    return deco


def evaluate(ws, write: bool = True) -> dict:
    from ..workspace import status

    # 驱动模式下的 agent 带 KNOSIS_DEPTH=1：不给它看测试分数，否则就是在针对 GT 调参。
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("evaluation is disabled inside agent runs (KNOSIS_DEPTH >= 1)")
    ws = Path(ws).resolve()
    state = status(ws)
    ds = load_dataset(state["benchmark"], state["scenario"], root=state["options"].get("root"))
    ids = [task["id"] for task in load_units(ws / "tasks/tasks.jsonl")]
    path = ws / "stages/4_decide" / state["output"] if state["output"] else None
    result = SCORERS[state["benchmark"]](ws, state, ds, path, ids)
    report = {"benchmark": state["benchmark"], "scenario": state["scenario"],
              "knowledge": state.get("knowledge", "K_final"), "n": len(ids), **result["metrics"],
              "reference": result.get("reference", {}), "usage": usage(ws)}
    if write:
        (ws / ".knosis/eval.json").write_text(
            json.dumps({**report, "items": result["items"]}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return report


def usage(ws) -> dict:
    """`stages/4_decide/used_units.jsonl`（每行 {id, used_units}）里知识被引用的情况。"""
    path = Path(ws) / "stages/4_decide/used_units.jsonl"
    units = {u["id"]: u for u in load_units(Path(ws) / "knowledge/units.jsonl")}
    if not path.exists():
        return {"reported": False, "units": len(units)}
    rows = load_units(path)
    cited = [uid for row in rows for uid in row.get("used_units", [])]
    return {
        "reported": True, "units": len(units), "predictions": len(rows),
        "with_knowledge": sum(bool(row.get("used_units")) for row in rows) / max(1, len(rows)),
        "distinct_units_used": len(set(cited) & set(units)),
        "unknown_units": sorted(set(cited) - set(units)),
        "inactive_units": sorted({uid for uid in cited if units.get(uid, {}).get("status") in INACTIVE}),
    }


def answers(path) -> dict:
    """JSONL 交付 → {id: answer}。"""
    return {row["id"]: row.get("answer") for row in load_units(path)}


def mean(rows, key) -> float:
    return sum(r[key] for r in rows) / max(1, len(rows))


from . import graph_qa, tabular  # noqa: E402,F401
