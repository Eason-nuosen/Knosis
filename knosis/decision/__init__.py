"""决策层：decide 产物如何打分，以及知识在决策中被如何使用。

每个数据集一个打分器 `score(ws, state, ds, path, ids) -> dict`，用 `@register("<数据集>")` 注册：
`path` 是交付文件（格式见导出器的 `output`），`ids` 是要打分的题目 id，`ds` 从原始数据目录重新加载（含 GT）。
返回 `{"metrics": {...}, "items": [{"id", "ok", "gold", ...}], "reference": {...}}`：
`evaluate` 在测试题上调用它；dev 反馈（`knowledge.feedback.submit`）在 dev 题上调用同一个函数。

知识本身对不对（与任务有没有用分开）由可选的 `score_knowledge(ws, state, ds) -> dict` 评，
用 `@register_knowledge("<数据集>")` 注册，结果写进评测报告的 `knowledge` 段；它可以读 GT，但结果不回给 agent。
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Callable

from ..knowledge import INACTIVE, all_ontology_units, layout, load_units, ontology_docs, skills

SCORERS: dict[str, Callable] = {}
KNOWLEDGE_SCORERS: dict[str, Callable] = {}


def register(name: str):
    def deco(fn):
        SCORERS[name] = fn
        return fn

    return deco


def register_knowledge(name: str):
    def deco(fn):
        KNOWLEDGE_SCORERS[name] = fn
        return fn

    return deco


def evaluate(ws, write: bool = True) -> dict:
    from ..workspace import open_dataset, status

    # 驱动模式下的 agent 带 KNOSIS_DEPTH=1：不给它看测试分数，否则就是在针对 GT 调参。
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("evaluation is disabled inside agent runs (KNOSIS_DEPTH >= 1)")
    ws = Path(ws).resolve()
    state = status(ws)
    ds = open_dataset(state["benchmark"], state["scenario"], state["options"])
    ids = [task["id"] for task in load_units(ws / "tasks/tasks.jsonl")] if state["output"] else []
    path = ws / "stages/4_decide" / state["output"] if state["output"] else None
    result = SCORERS[state["benchmark"]](ws, state, ds, path, ids)
    report = {"benchmark": state["benchmark"], "scenario": state["scenario"],
              "knowledge": state.get("knowledge", "K_final"), "n": len(ids), **result["metrics"],
              "reference": result.get("reference", {}), "usage": usage(ws)}
    report["knowledge_summary"] = summary(ws)
    if state["benchmark"] in KNOWLEDGE_SCORERS:
        report["knowledge"] = KNOWLEDGE_SCORERS[state["benchmark"]](ws, state, ds)
    report["usage_effect"] = test_usage(ws, result["items"])
    if write:
        (ws / ".knosis/eval.json").write_text(
            json.dumps({**report, "items": result["items"]}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return report


def usage(ws) -> dict:
    """`stages/4_decide/used_units.jsonl`（每行 {id, used_units}）里知识被引用的情况。"""
    path = Path(ws) / "stages/4_decide/used_units.jsonl"
    units = {u["id"]: u for u in load_units(layout(ws).units)}
    if not path.exists():
        return {"reported": False, "units": len(units)}
    rows = load_units(path)
    cited = [uid for row in rows for uid in row.get("used_units", [])]
    # 本体单元与 skill 也可以被引用。
    known = set(units) | {u["id"] for u in all_ontology_units(ontology_docs(ws))}
    known |= {skills.skill_id(s) for s in skills.load_skills(ws)}
    return {
        "reported": True, "units": len(units), "predictions": len(rows),
        "with_knowledge": sum(bool(row.get("used_units")) for row in rows) / max(1, len(rows)),
        "distinct_units_used": len(set(cited) & known),
        "unknown_units": sorted(set(cited) - known),
        "inactive_units": sorted({uid for uid in cited if units.get(uid, {}).get("status") in INACTIVE}),
    }


def test_usage(ws, items) -> dict:
    """测试题上每条被引用知识的使用效果：用到时 / 没用到时的正确率。只写进评测报告，不写回知识层（否则测试结果会经知识库泄漏）。"""
    path = Path(ws) / "stages/4_decide/used_units.jsonl"
    if not path.exists() or not items or "ok" not in items[0]:
        return {"reported": False}
    ok = {str(i["id"]): bool(i["ok"]) for i in items}
    cited = {str(r["id"]): set(r.get("used_units", [])) for r in load_units(path) if str(r["id"]) in ok}
    rows = []
    for uid in sorted(set().union(*cited.values())) if cited else []:
        hit = [ok[t] for t in cited if uid in cited[t]]
        other = [ok[t] for t in cited if uid not in cited[t]]
        rows.append({"unit": uid, "n_used": len(hit), "acc_used": mean_bool(hit),
                     "n_other": len(other), "acc_other": mean_bool(other)})
    return {"reported": True, "units": sorted(rows, key=lambda r: -r["n_used"])}


def mean_bool(values):
    return sum(values) / len(values) if values else None


def summary(ws) -> dict:
    """知识层概况：各形式 / 状态的单元数，各结论的证据数，带可执行检查的单元数。"""
    from ..knowledge import load_evidence

    units = load_units(layout(ws).units)
    count = lambda values: dict(sorted(Counter(values).items()))  # noqa: E731
    from ..knowledge import scope_of

    return {"units": len(units), "scopes": count(scope_of(u) for u in units),
            "levels": count("meta" if scope_of(u) in ("method", "usage") else "object" for u in units),
            "forms": count(u["form"] for u in units), "statuses": count(u["status"] for u in units),
            "with_check": sum("check" in u for u in units),
            "evidence": count(e["verdict"] for e in load_evidence(ws)),
            "consolidate": count(a["op"] for a in load_units(layout(ws).actions)) if layout(ws).actions.exists() else {}}


def answers(path) -> dict:
    """JSONL 交付 → {id: answer}。"""
    return {row["id"]: row.get("answer") for row in load_units(path)}


def mean(rows, key) -> float:
    return sum(r[key] for r in rows) / max(1, len(rows))


from . import (  # noqa: E402,F401
    alphabench, bibench, burr, graph_qa, kramabench, llm_srbench, newtonbench, relbench, spreadsheetbench, tabular, text,
    traces, whoandwhen,
)
