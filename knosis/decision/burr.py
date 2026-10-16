"""Burr 打分：移植上游 `evaluator/metrics` 与 `mapping_parser` 对 JSON 映射的比较（不需要 LLM）。

类、关系（object property）、属性（data property）各算 P / R / F1，两种口径：
- mapping_based：类比 (URI 模式中的列, 条件, join)；关系 / 属性比 (join, 列, 表达式中的列, 模式, 常量, 条件)，
  这些都为空时比两端类；按多重集合计数（上游 Counter）。
- name_based：类比类名；关系 / 属性比清洗后的属性名与两端类名；按集合计数。
GT 是 D2RQ 的 .ttl（iswc、npd）时上游先转成 D2RQ 对象再比较，这里尚未支持。
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import answers, mean, register
from ..data import read

KINDS = ("cls", "rel", "attr")


def attr(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def pattern(text) -> frozenset:
    text = text[0] if isinstance(text, list) else text
    return frozenset(attr(re.sub(r"\|(urlify|encode|urlencode)", "", p)) for p in re.findall(r"@@(.*?)@@", text or ""))


def conditions(value) -> frozenset:
    return frozenset(re.sub(r"\s+", " ", c).strip().lower() for c in ([value] if isinstance(value, str) else value or []))


def joins(value) -> frozenset:
    return frozenset(frozenset(attr(side) for side in j.split("=")) for j in value or [])


def clean_property(name: str) -> str:
    """上游 equality_by_property_name 的清洗：去掉空格、下划线、连字符与 has/is/of/the。"""
    for filler in (" ", "_", "-", "has", "is", "of", "the"):
        name = name.replace(filler, "")
    return name.strip().lower()


def elements(mapping: dict) -> dict:
    """{口径: {cls|rel|attr: [可比较的键]}}。"""
    classes = mapping.get("classes", [])
    by_name = {c.get("name", c["class"]): c for c in classes}

    def class_key(c):
        return (conditions(c.get("condition")), pattern(c.get("id")), joins(c.get("join")))

    def ref(name, mapping_based):
        c = by_name.get(name)
        if c is None:
            return None if name is None else ("?", name.lower())
        return class_key(c) if mapping_based else c["class"].strip().lower()

    def edge_key(p):
        sql = frozenset(attr(a) for a in re.findall(r"\b\w+\.\w+\b", p.get("sqlExpression") or ""))
        key = (joins(p.get("join")), attr(p["column"]) if p.get("column") else None, sql,
               pattern(p.get("pattern")), p.get("constantValue"), conditions(p.get("condition")))
        if key == (frozenset(), None, frozenset(), frozenset(), None, frozenset()):
            return ("classes", ref(owner(p), True), ref(target(p), True))
        return key

    def name_key(p):
        return (clean_property(p["property"]), ref(owner(p), False), ref(target(p), False))

    edges = {"rel": mapping.get("object_properties", []), "attr": mapping.get("data_properties", [])}
    return {
        "mapping_based": {"cls": [class_key(c) for c in classes], **{k: [edge_key(p) for p in v] for k, v in edges.items()}},
        "name_based": {"cls": [c["class"].strip().lower() for c in classes], **{k: [name_key(p) for p in v] for k, v in edges.items()}},
    }


def owner(p):
    return p.get("belongsToClassMap", p.get("belongsToClass"))


def target(p):
    return p.get("refersToClassMap", p.get("refersToClass"))


def bag_precision_recall(gold: list, pred: list) -> tuple[float, float]:
    g, p = Counter(gold), Counter(pred)
    hit = sum((g & p).values())
    precision = hit / sum(p.values()) if p else float(not g)
    recall = hit / sum(g.values()) if g else float(not p)
    return precision, recall


def set_precision_recall(gold: list, pred: list) -> tuple[float, float]:
    g, p = set(gold), set(pred)
    if not g and not p:
        return 1.0, 1.0
    return (len(g & p) / len(p) if p else 0.0), (len(g & p) / len(g) if g else 0.0)


def compare(gold: dict, pred: dict) -> dict:
    result = {}
    g, p = elements(gold), elements(pred)
    for family, fn in (("mapping_based", bag_precision_recall), ("name_based", set_precision_recall)):
        for kind in KINDS:
            precision, recall = fn(g[family][kind], p[family][kind])
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            result |= {f"{family}_{kind}_precision": precision, f"{family}_{kind}_recall": recall, f"{family}_{kind}_f1": f1}
    return result


def gold_mapping(answer) -> dict:
    """单个 mapping.json，或真实库 mappings/ 下多个文件（合并）。"""
    paths = answer if isinstance(answer, list) else [answer]
    if any(Path(p).suffix == ".ttl" for p in paths):
        raise NotImplementedError("D2RQ (.ttl) ground truth is not supported yet")
    merged = {"classes": [], "object_properties": [], "data_properties": []}
    for p in paths:
        for key, values in read(p).items():
            merged.setdefault(key, []).extend(values)
    return merged


def summary(rows) -> dict:
    keys = [f"{fam}_{kind}_{m}" for fam in ("mapping_based", "name_based") for kind in KINDS for m in ("precision", "recall", "f1")]
    return {k: mean(rows, k) for k in keys}


@register("burr")
def score(ws, state, ds, path, ids) -> dict:
    gold = {t.id: t for t in ds.tasks}
    predictions = answers(path)
    items = []
    for tid in ids:
        g = gold_mapping(gold[tid].answer)
        metrics = compare(g, predictions.get(tid) or {})
        overall = sum(metrics[f"mapping_based_{k}_f1"] for k in KINDS) / 3
        items.append({"id": tid, "ok": overall == 1.0, "score": overall, **metrics, "gold": g})
    return {"metrics": {"score": mean(items, "score"), "accuracy": mean(items, "ok"),
                        "missing": sum(tid not in predictions for tid in ids), **summary(items)},
            "items": items, "reference": {}}
