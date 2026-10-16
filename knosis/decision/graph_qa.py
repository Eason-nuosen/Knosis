"""图问答（NGDBench）打分：答案集合 EM / F1。"""

from __future__ import annotations

from collections import defaultdict

from ..knowledge import load_units
from . import register


def scalar(value) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return f"{float(value):.6g}"
    if value is None:
        return "null"
    text = str(value).strip()
    try:
        return f"{float(text):.6g}"
    except ValueError:
        return text


def answer_set(value) -> frozenset:
    """标量 → 单元素集合；列表去重；字典行只比较取值（不要求与 Cypher 的返回别名一致）。"""
    items = value if isinstance(value, list) else [value]
    return frozenset(
        tuple(sorted(scalar(v) for v in item.values())) if isinstance(item, dict) else scalar(item) for item in items
    )


def f1(pred: frozenset, gold: frozenset) -> float:
    if not pred and not gold:
        return 1.0
    hit = len(pred & gold)
    return 2 * hit / (len(pred) + len(gold)) if hit else 0.0


def summarize(rows) -> dict:
    n = len(rows)
    return {"n": n, "answer_set_em": sum(r["em"] for r in rows) / max(1, n),
            "answer_set_f1": sum(r["f1"] for r in rows) / max(1, n)}


@register("ngdbench")
def score(ws, state, ds) -> dict:
    gold = {t.id: t for t in ds.tasks}
    tasks = load_units(ws / "tasks/tasks.jsonl")
    predictions = {p["id"]: p.get("answer") for p in load_units(ws / "stages/4_decide" / state["output"])}
    rows, noise, by_kind = [], [], defaultdict(list)
    for task in tasks:
        g = answer_set(gold[task["id"]].answer)
        p = answer_set(predictions[task["id"]]) if task["id"] in predictions else frozenset()
        row = {"em": p == g, "f1": f1(p, g)}
        rows.append(row)
        by_kind[task["kind"]].append(row)
        # 参照：直接照抄含噪观测图上的答案能得几分。
        n = answer_set(gold[task["id"]].meta.get("noise_answer"))
        noise.append({"em": n == g, "f1": f1(n, g)})
    return {**summarize(rows), "missing": sum(t["id"] not in predictions for t in tasks),
            "by_kind": {k: summarize(v) for k, v in sorted(by_kind.items())},
            "reference": {"noisy_graph_answer": summarize(noise)}}
