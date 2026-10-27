"""AlphaBench (evaluate, upstream T2) scoring: given a factor expression, predict its performance over the evaluation window.

GT is computed on the fly from the IC / RankIC truth tables following upstream `benchmark/utils/data_builder/base_eval/stats.py`:
mean_ic, mean_rankic, icir, turnover proxy (IC sign-flip rate), win rate, skewness; |mean_ic| < 0.01 is Noise,
otherwise Positive / Negative by sign; the four dimensions (Performance=|ICIR|, Stability=1-flip rate, WinRate, Skewness)
get 1-5 by quantile within factors of the same signal; Noise gets 1 everywhere.
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
    """One row per factor: statistics, signal, 1-5 scores on the four dimensions. Factors with fewer than 20 observed days get NaN statistics and are marked Noise."""
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
    # A constant prediction carries no ranking information; Spearman is undefined.
    return number(frame["p"].corr(frame["g"], method="spearman")) if len(frame) > 2 and frame["p"].nunique() > 1 else None


def summarize(rows, gold) -> dict:
    """rows: per-task prediction dicts (fields may be missing); gold: the matching GT rows."""
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
        # Precision@K: overlap between the top K by predicted mean_ic and the top K by true value (K = 10%).
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
    # Reference: predict Noise for everything and mean_ic = 0.
    reference = summarize([{"signal": "Noise", "mean_ic": 0.0, "mean_rankic": 0.0}] * len(ids), gold)
    return {"metrics": metrics, "items": items, "reference": {"all_noise_zero_ic": reference}}
