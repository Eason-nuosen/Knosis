"""BI-Bench 打分：移植上游 `tools/run_large_models.py` 的 compare_dataframes 口径。"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import answers, mean, register

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "--"}


def parse(value):
    """'$1.5' → 1.5，'8.95%' → 0.0895，数字串 → float，其余原样。"""
    if not isinstance(value, str):
        return value
    text = value.strip()
    for mark, scale in (("$", 1), ("%", 100)):
        if mark in (text[:1], text[-1:]):
            try:
                return float(text.replace(mark, "")) / scale
            except ValueError:
                return text
    try:
        return float(text)
    except ValueError:
        return text


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def missing(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in MISSING
    if value is None or pd.isna(value):
        return True
    return math.isinf(number(value)) if number(value) is not None else False


def same(a, b, rtol=1e-3, atol=0.5) -> bool:
    a, b = parse(a), parse(b)
    x, y = number(a), number(b)
    if x is not None and y is not None:
        return bool(np.isclose(x, y, rtol=rtol, atol=atol))
    try:
        return pd.to_datetime(a) == pd.to_datetime(b)
    except (ValueError, TypeError, OverflowError):
        return str(a).strip() == str(b).strip()


def flat(frame: pd.DataFrame, max_rows=100) -> list:
    """上游的规范化：按各列字符串排序、截前 100 行、展平，缺失值记为 0。"""
    frame = frame.sort_values(by=list(frame.columns), key=lambda c: c.astype(str), kind="mergesort").iloc[:max_rows]
    return [0.0 if missing(v) else v for v in frame.to_numpy().flatten().tolist()]


def matches(gold: pd.DataFrame, pred: pd.DataFrame) -> bool:
    if gold.shape == (1, 1):
        return any(same(gold.iloc[0, 0], v) for v in flat(pred, len(pred)))
    if gold.shape != pred.shape:
        return False
    remaining = flat(pred)
    for v in flat(gold):
        best, best_diff = None, math.inf
        for i, w in enumerate(remaining):
            x, y = number(v), number(w)
            if x is not None and y is not None:  # 都是数：取 rtol=1e-2 / atol=0.5 内最接近的
                if np.isclose(x, y, rtol=1e-2, atol=0.5) and abs(x - y) < best_diff:
                    best, best_diff = i, abs(x - y)
            elif same(v, w):  # 否则按 $ / % / 日期 / 字符串比较，命中即停
                best = i
                break
        if best is None:
            return False
        remaining.pop(best)
    return not remaining


def table(answer) -> pd.DataFrame:
    if isinstance(answer, dict):
        return pd.DataFrame(answer["rows"], columns=answer["columns"])
    if isinstance(answer, list):
        return pd.DataFrame(answer)
    return pd.DataFrame({"result": [answer]})


def preview(frame: pd.DataFrame, rows=20) -> dict:
    return {"columns": [str(c) for c in frame.columns], "rows": frame.head(rows).astype(str).to_numpy().tolist(),
            "n_rows": len(frame)}


@register("bibench")
def score(ws, state, ds, path, ids) -> dict:
    gold = {t.id: t.answer for t in ds.tasks}
    predictions = answers(path)
    items = []
    for tid in ids:
        refs = [pd.read_csv(p) for p in gold[tid] if p.exists()]
        ok = tid in predictions and predictions[tid] is not None and any(matches(g, table(predictions[tid])) for g in refs)
        items.append({"id": tid, "ok": ok, "gold": [preview(g) for g in refs]})
    return {"metrics": {"success": mean(items, "ok"), "missing": sum(t not in predictions for t in ids)},
            "items": items, "reference": {}}
