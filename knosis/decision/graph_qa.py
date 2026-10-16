"""图问答（NGDBench）打分：答案集合 EM / F1。"""

from __future__ import annotations

from collections import defaultdict

from . import answers, mean, register


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
    """标量 → 单元素集合；列表去重；字典行只比较取值（不要求与 Cypher 的返回别名一致），单列字典等同于它的值。"""
    items = value if isinstance(value, list) else [value]
    return frozenset(
        (scalar(*item.values()) if len(item) == 1 else tuple(sorted(scalar(v) for v in item.values())))
        if isinstance(item, dict) else scalar(item) for item in items
    )


def f1(pred: frozenset, gold: frozenset) -> float:
    if not pred and not gold:
        return 1.0
    hit = len(pred & gold)
    return 2 * hit / (len(pred) + len(gold)) if hit else 0.0


def summarize(rows) -> dict:
    return {"answer_set_em": mean(rows, "ok"), "answer_set_f1": mean(rows, "f1")}


@register("ngdbench")
def score(ws, state, ds, path, ids) -> dict:
    gold = {t.id: t for t in ds.tasks}
    predictions = answers(path)
    items, noise, by_kind = [], [], defaultdict(list)
    for tid in ids:
        task = gold[tid]
        g = answer_set(task.answer)
        p = answer_set(predictions[tid]) if tid in predictions else frozenset()
        item = {"id": tid, "kind": task.kind, "ok": p == g, "f1": f1(p, g), "gold": task.answer}
        items.append(item)
        by_kind[task.kind].append(item)
        # 参照：直接照抄含噪观测图上的答案能得几分。
        n = answer_set(task.meta.get("noise_answer"))
        noise.append({"ok": n == g, "f1": f1(n, g)})
    metrics = {**summarize(items), "missing": sum(tid not in predictions for tid in ids),
               "by_kind": {k: {"n": len(v), **summarize(v)} for k, v in sorted(by_kind.items())}}
    return {"metrics": metrics, "items": items, "reference": {"noisy_graph_answer": summarize(noise)}}
