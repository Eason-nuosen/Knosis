"""BI-Bench 打分：移植上游 `tools/run_large_models.py` 的 compare_dataframes 口径；外加 join 发现的本体评分。"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ..knowledge import ontology
from ..knowledge import ontology_docs
from . import answers, mean, register, register_knowledge

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


# ---------------------------------------------------------------- 本体（join 发现）评分


def key(name: str) -> str:
    """表名比较用：去掉非字母数字、转小写（CSV 文件名与 Power BI 表名只差空格和标点）。"""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def pairs(model: dict) -> set[frozenset]:
    """core 层的关系 → {(表, 列), (表, 列)} 的无向集合；只比第一组列。"""
    out = set()
    for r in model.get("relationships", []):
        if r.get("from_columns") and r.get("to_columns"):
            out.add(frozenset({(r["from"], r["from_columns"][0]), (r["to"], r["to_columns"][0])}))
    return out


def index(model: dict, case: str) -> dict[str, str]:
    """Power BI 表名（按 CSV 文件名归一）→ core 层 dataset 名；先找该用例的 CSV 路径，再找同源用例（-1/-2…）。"""
    raw = [((ontology.eob_data(d).get("raw") or {}).get("path"), d["name"]) for d in model.get("datasets", [])]
    paths = [(Path(p), n) for p, n in raw if p]
    for match in (lambda p: p.parent.name == case, lambda p: p.parent.name.split("-")[0] == case.split("-")[0]):
        names = {key(p.stem): n for p, n in paths if match(p)}
        if names:
            return names
    return {key(d["source"]): d["name"] for d in model.get("datasets", []) if d.get("source")}


def gold_pairs(metadata: Path, model: dict, case: str) -> set[frozenset]:
    """`_relationships.csv` 的 GT（Power BI 项目作者定义的 join）→ 无向 join 集合。"""
    if not (metadata / "_relationships.csv").is_file():
        return set()
    names = index(model, case)
    tables = {r["ID"]: r["Name"] for r in csv.DictReader(open(metadata / "_tables.csv"))}
    lookup = {}
    for r in csv.DictReader(open(metadata / "_columns.csv")):
        table = names.get(key(tables.get(r["TableID"], "")))
        if table:
            lookup[r["ID"]] = (table, r["ExplicitName"] or r["InferredName"])
    out = set()
    for r in csv.DictReader(open(metadata / "_relationships.csv")):
        a, b = lookup.get(r["FromColumnID"]), lookup.get(r["ToColumnID"])
        if a and b:
            out.add(frozenset({a, b}))
    return out


def score_pairs(pred: set[frozenset], gold: set[frozenset]) -> dict:
    hit = len(pred & gold)
    p, r = hit / len(pred) if pred else 0.0, hit / len(gold) if gold else 0.0
    return {"n_pred": len(pred), "n_gold": len(gold), "n_hit": hit, "precision": p, "recall": r,
            "f1": 2 * p * r / (p + r) if p + r else 0.0}


def join_report(knowledge, ds) -> dict:
    """知识层里的全部本体 → 各用例的 join 发现分数；没有本体时 reported=False。"""
    docs = {n: d for n, d in ontology_docs(knowledge).items() if "semantic_model" in d}
    if not docs:
        return {"reported": False}
    bench = Path(ds.root) if Path(ds.root).name == "bi-bench" else Path(ds.root).parent  # 单用例时 root 是 bi-bench/<用例>/
    meta = bench.parent / "tools/data_management_tools/metadata"
    scores = {name: {case: score_pairs(pairs(docs[name]["semantic_model"]),
                                       gold_pairs(meta / case, docs[name]["semantic_model"], case))
                     for case in (t.id for t in ds.tasks)}
              for name in docs}
    rows = [s for case in scores.values() for s in case.values()]
    return {"reported": True, "units": len(docs), "cases": [t.id for t in ds.tasks], "scores": scores,
            "mean": {k: mean(rows, k) for k in ("precision", "recall", "f1")}}


@register_knowledge("bibench")
def score_knowledge(ws, state, ds) -> dict:
    ws = Path(ws)
    result = {"ontology": join_report(ws, ds)}
    inherited = ws / "stages/0_inherit"
    if (inherited / "kb").is_dir():
        result["K_inherit"] = join_report(inherited, ds)
    return result
