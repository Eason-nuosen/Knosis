"""AlphaBench（evaluate，对应上游 T2）打分：给定因子表达式，预测它在评估窗口内的表现。

GT 由 IC / RankIC 真值表按上游 `benchmark/utils/data_builder/base_eval/stats.py` 的口径现算：
mean_ic、mean_rankic、icir、换手代理（IC 符号翻转率）、胜率、偏度；|mean_ic| < 0.01 为 Noise，
否则按符号分 Positive / Negative；四个维度（Performance=|ICIR|、Stability=1-翻转率、WinRate、Skewness）
在同类因子内按分位数给 1–5 分，Noise 全为 1。
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from . import answers, register

NOISE_IC = 0.01
MIN_OBS = 20
DIMENSIONS = {"Performance": "icir", "Stability": "turnover_rate", "WinRate": "win_rate", "Skewness": "skewness"}


def window(path, start, end) -> pd.DataFrame:
    table = pd.read_csv(path, index_col="datetime", parse_dates=["datetime"]).sort_index().dropna(axis=1, how="all")
    return table.loc[pd.Timestamp(start):pd.Timestamp(end)]


def flip_ratio(series: pd.Series) -> float:
    signs = np.sign(series.dropna().to_numpy())
    nonzero = signs[signs != 0]
    return float((nonzero[1:] * nonzero[:-1] < 0).sum() / max(len(signs) - 1, 1))


def quintile(values: pd.Series) -> pd.Series:
    return np.ceil(values.rank(pct=True) * 5).clip(1, 5).astype(int)


@lru_cache(maxsize=4)
def factor_stats(ic_path, rankic_path, start, end) -> pd.DataFrame:
    """每个因子一行：统计量、signal、四个维度的 1–5 分。观测少于 20 天的因子统计量为 NaN，记为 Noise。"""
    ic, rankic = window(ic_path, start, end), window(rankic_path, start, end)
    enough = ic.count() >= MIN_OBS
    stats = pd.DataFrame({
        "mean_ic": ic.mean(), "std_ic": ic.std(),
        "mean_rankic": rankic.mean().where(rankic.count() >= MIN_OBS),
        "turnover_rate": ic.apply(flip_ratio),
        "skewness": ic.skew(),
    }).where(enough, axis=0)
    stats["icir"] = stats["mean_ic"] / stats["std_ic"]
    stats["rankicir"] = stats["mean_rankic"] / rankic.std()
    sign = np.sign(stats["mean_ic"])
    stats["win_rate"] = (((ic > 0).sum() * (sign > 0) + (ic < 0).sum() * (sign < 0)) / ic.count()).where(enough)
    stats["signal"] = np.where(stats["mean_ic"].abs() >= NOISE_IC,
                               np.where(stats["mean_ic"] > 0, "Positive", "Negative"), "Noise")
    for dim in DIMENSIONS:
        stats[dim] = 1
    for label in ("Positive", "Negative"):
        group = stats["signal"] == label
        sub = stats[group]
        stats.loc[group, "Performance"] = quintile(sub["icir"].abs())
        stats.loc[group, "Stability"] = quintile(1 - sub["turnover_rate"].fillna(1))
        stats.loc[group, "WinRate"] = quintile(sub["win_rate"].fillna(0.5))
        stats.loc[group, "Skewness"] = quintile(sub["skewness"].fillna(0))
    return stats


def number(x):
    return None if pd.isna(x) else float(x)


def gold_record(row) -> dict:
    return {"signal": row["signal"], "mean_ic": number(row["mean_ic"]), "mean_rankic": number(row["mean_rankic"]),
            "scores": {dim: int(row[dim]) for dim in DIMENSIONS}}


def spearman(pred, gold) -> float | None:
    frame = pd.DataFrame({"p": pred, "g": gold}).dropna()
    # 常数预测没有排序信息，Spearman 无定义。
    return number(frame["p"].corr(frame["g"], method="spearman")) if len(frame) > 2 and frame["p"].nunique() > 1 else None


def summarize(rows, gold) -> dict:
    """rows：每题的预测 dict（可缺字段）；gold：对应的 GT 行。"""
    n = len(rows)
    metrics = {"signal_accuracy": sum(r.get("signal") == g["signal"] for r, g in zip(rows, gold)) / max(1, n)}
    for key in ("mean_ic", "mean_rankic"):
        pairs = [(r[key], g[key]) for r, g in zip(rows, gold) if r.get(key) is not None and g[key] is not None]
        if pairs:
            p, g = map(np.asarray, zip(*pairs))
            metrics[f"{key}_mae"] = float(np.mean(np.abs(p - g)))
            metrics[f"{key}_spearman"] = spearman(p, g)
    with_ic = [(r["mean_ic"], g["mean_ic"]) for r, g in zip(rows, gold) if r.get("mean_ic") is not None and g["mean_ic"] is not None]
    if with_ic:
        # Precision@K：按预测 mean_ic 取前 K，与按真值取前 K 的重合率（K = 10%）。
        k = max(1, len(with_ic) // 10)
        top = lambda values: set(np.argsort(-np.asarray(values))[:k])  # noqa: E731
        metrics["precision_at_10pct"] = len(top([p for p, _ in with_ic]) & top([g for _, g in with_ic])) / k
    scored = [(r["scores"], g["scores"]) for r, g in zip(rows, gold) if isinstance(r.get("scores"), dict)]
    for dim in DIMENSIONS:
        pairs = [(int(p[dim]), g[dim]) for p, g in scored if dim in p]
        if pairs:
            metrics[f"{dim}_accuracy"] = sum(p == g for p, g in pairs) / len(pairs)
            metrics[f"{dim}_mae"] = sum(abs(p - g) for p, g in pairs) / len(pairs)
    return metrics


@register("alphabench")
def score(ws, state, ds, path, ids) -> dict:
    opts = state["options"]
    stats = factor_stats(str(ds.files["ic"]), str(ds.files["rankic"]),
                         opts.get("start", "2021-01-01"), opts.get("end", "2025-06-30"))
    predictions = answers(path)
    rows = [predictions.get(i) or {} for i in ids]
    gold = [gold_record(stats.loc[i.removeprefix("factor/")]) for i in ids]
    items = []
    for i, r, g in zip(ids, rows, gold):
        item = {"id": i, "ok": r.get("signal") == g["signal"], "gold": g}
        if r.get("mean_ic") is not None and g["mean_ic"] is not None:
            item["mean_ic_error"] = float(r["mean_ic"]) - g["mean_ic"]
        items.append(item)
    metrics = {**summarize(rows, gold), "missing": sum(i not in predictions for i in ids)}
    # 参照：全部判为 Noise、mean_ic 猜 0。
    reference = summarize([{"signal": "Noise", "mean_ic": 0.0, "mean_rankic": 0.0}] * len(ids), gold)
    return {"metrics": metrics, "items": items, "reference": {"all_noise_zero_ic": reference}}
