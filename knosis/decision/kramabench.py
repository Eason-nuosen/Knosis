"""KramaBench scoring: ports the non-LLM metrics of upstream `benchmark/metrics.py`, per answer_type.

- numeric_exact / string_exact: upstream Success (numbers tolerate rounding error, strings are case-insensitive)
- numeric_approximate: upstream RAE score = 1 / (1 + relative error); ok means relative error ≤ 1%
- list_exact: upstream F1 (strings case-insensitive, numbers relative error < 1e-6)
- list_approximate: upstream F1Approximate, numbers relative error ≤ 1%; upstream judges string elements as paraphrases with an LLM, here this falls back to exact match after normalization
- string_approximate: upstream judges paraphrase with an LLM (llm_paraphrase), here this falls back to exact match after normalization (alphanumerics only, lowercase)
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from . import answers, mean, register

LLM_FALLBACK = "string_approximate and string elements of list_approximate: upstream judges paraphrase with an LLM, here exact match after normalization"


def number(value):
    """Upstream try_convert_to_number: a number or numeric string (percent sign supported) -> float, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    try:
        return float(text[:-1].strip()) / 100 if text.endswith("%") else float(text)
    except ValueError:
        return None


def normalize(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def success(pred, gold) -> float:
    if pred is None:
        return 0.0
    p, g = number(pred), number(gold)
    if p is not None and g is not None:
        if p == g:
            return 1.0
        if isinstance(p, int) and isinstance(g, int):
            return 0.0
        if g == 0:
            return float(abs(p) < 1e-6)
        diff = abs(p - g)
        return float(diff / abs(g) < 1e-6 or diff < 1e-6 or diff < max(abs(p), abs(g)) * 1e-4)
    return float(str(pred).strip().lower() == str(gold).strip().lower())


def as_list(pred) -> list:
    if isinstance(pred, list):
        return pred
    text = str(pred)
    try:
        value = json.loads(text)
        return value if isinstance(value, list) else [value]
    except json.JSONDecodeError:
        return [item.strip() for item in text.split(",") if item.strip()]


def list_f1(pred, gold, tolerance, same_string) -> float:
    if pred is None:
        return 0.0
    pred = as_list(pred)
    if not gold:
        return float(not pred)
    matched, hits = set(), 0
    for g in gold:
        for j, p in enumerate(pred):
            if isinstance(g, str):
                found = same_string(str(p), g)
            else:
                pp = number(p)
                found = pp is not None and abs(pp - g) / max(abs(g), 1e-12) <= tolerance
            if found:
                matched.add(j)
                hits += 1
                break
    recall, precision = hits / len(gold), len(matched) / len(pred) if pred else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def score_answer(kind: str, pred, gold) -> tuple[float, bool]:
    """Returns (score, is correct)."""
    if kind in ("numeric_exact", "string_exact"):
        s = success(pred, gold)
        return s, s == 1.0
    if kind == "numeric_approximate":
        p = number(pred)
        if p is None:
            return 0.0, False
        rae = abs(p - gold) / abs(gold) if gold else abs(p)
        return 1 / (1 + rae), rae <= 0.01
    if kind == "list_exact":
        s = list_f1(pred, gold, 1e-6, lambda p, g: p.strip().lower() == g.strip().lower())
        return s, s == 1.0
    if kind == "list_approximate":
        s = list_f1(pred, gold, 0.01, lambda p, g: normalize(p) == normalize(g))
        return s, s == 1.0
    s = float(pred is not None and normalize(pred) == normalize(gold))  # string_approximate
    return s, s == 1.0


@register("kramabench")
def score(ws, state, ds, path, ids) -> dict:
    gold = {t.id: t for t in ds.tasks}
    predictions = answers(path)
    items, by_kind = [], defaultdict(list)
    for tid in ids:
        task = gold[tid]
        value, ok = score_answer(task.kind, predictions.get(tid), task.answer)
        item = {"id": tid, "answer_type": task.kind, "ok": ok, "score": value, "gold": task.answer}
        items.append(item)
        by_kind[task.kind].append(item)
    metrics = {"accuracy": mean(items, "ok"), "score": mean(items, "score"),
               "missing": sum(tid not in predictions for tid in ids),
               "by_answer_type": {k: {"n": len(v), "accuracy": mean(v, "ok"), "score": mean(v, "score")}
                                  for k, v in sorted(by_kind.items())},
               "note": LLM_FALLBACK}
    return {"metrics": metrics, "items": items, "reference": {}}
