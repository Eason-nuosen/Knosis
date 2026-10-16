"""决策层：decide 阶段的产物如何打分，以及知识在决策中被如何使用。

`evaluate(ws)` 从原始数据目录重新读取 GT（GT 从不进入工作区），按数据集调用打分器，
结果写到 `.knosis/eval.json`。新增数据集的评测：写一个 `scorer(ws, state, ds) -> dict`，
用 `@register("<数据集>")` 注册。
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

    # 驱动模式下的 agent 带 KNOSIS_DEPTH=1：不给它看分数，否则就是在针对 GT 调参。
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("evaluation is disabled inside agent runs (KNOSIS_DEPTH >= 1)")
    ws = Path(ws).resolve()
    state = status(ws)
    ds = load_dataset(state["benchmark"], state["scenario"], root=state["options"].get("root"))
    report = {"benchmark": state["benchmark"], "scenario": state["scenario"],
              "knowledge": state.get("knowledge", "K_final"), **SCORERS[state["benchmark"]](ws, state, ds)}
    report["usage"] = usage(ws)
    if write:
        (ws / ".knosis/eval.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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


from . import graph_qa, tabular  # noqa: E402,F401
