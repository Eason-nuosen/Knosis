"""AlphaBench（evaluate）：给因子表达式，预测其在评估窗口内的 IC 表现。

agent 只拿到评估窗口开始之前的行情（Qlib 二进制 → parquet 面板），可以自己在历史上验证因子；
IC / RankIC 真值表与窗口内的行情都不进工作区。generate 场景需要 Qlib 现算新因子的 IC，本地未装 Qlib，暂不支持。
"""

from __future__ import annotations

import random
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from ...decision.alphabench import factor_stats
from . import register, render, split


def read_bin(path: Path, calendar: list[str]) -> pd.Series:
    """Qlib 的 .day.bin：float32，第一个数是在交易日历里的起始下标。"""
    values = np.fromfile(path, dtype="<f4")
    start = int(values[0])
    return pd.Series(values[1:], index=pd.to_datetime(calendar[start:start + len(values) - 1]))


def market_panel(qlib: Path, universe: str, cutoff: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """截止 `cutoff`（不含）之前、历史上进过该指数的股票的日频面板与成分区间。"""
    calendar = (qlib / "calendars/day.txt").read_text().split()
    members = pd.read_csv(qlib / f"instruments/{universe}.txt", sep="\t", names=["instrument", "start", "end"])
    members = members[members["start"] < cutoff]
    members["end"] = members["end"].where(members["end"] < cutoff, (pd.Timestamp(cutoff) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    frames = []
    for name in sorted(members["instrument"].unique()):
        folder = qlib / "features" / name.lower()
        frame = pd.DataFrame({p.name.split(".")[0]: read_bin(p, calendar) for p in sorted(folder.glob("*.day.bin"))})
        frame = frame[frame.index < pd.Timestamp(cutoff)]
        frames.append(frame.rename_axis("datetime").reset_index().assign(instrument=name))
    panel = pd.concat(frames, ignore_index=True)
    return panel[["datetime", "instrument", *[c for c in panel if c not in ("datetime", "instrument")]]], members


def vocabulary(expressions) -> tuple[str, str]:
    operators = Counter(op for e in expressions for op in re.findall(r"([A-Z][A-Za-z0-9]*)\(", e))
    fields = Counter(f for e in expressions for f in re.findall(r"\$[a-z_]+", e))
    return ", ".join(f"`{k}`" for k, _ in operators.most_common()), ", ".join(f"`{k}`" for k, _ in fields.most_common())


@register("alphabench")
def export(ds, ws: Path, write_data=True, start="2021-01-01", end="2025-06-30", dev=50, limit=250, seed=0, **opts) -> dict:
    """`start`/`end`：评估窗口（上游 Overall 区间）；题目按 Positive / Negative / Noise = 4:4:2 分层抽样（上游 100:100:50）。"""
    assert ds.scenario == "evaluate", "只支持 evaluate；generate 需要 Qlib 现算新因子的 IC"
    pool = ds.read("factor_pool")
    stats = factor_stats(str(ds.files["ic"]), str(ds.files["rankic"]), start, end)
    rng, total = random.Random(seed), dev + limit
    sampled = []
    for label, share in (("Positive", 0.4), ("Negative", 0.4), ("Noise", 0.2)):
        names = sorted(n for n in stats.index[stats["signal"] == label] if n in pool)
        sampled += rng.sample(names, min(len(names), round(total * share)))
    items = [{"id": f"factor/{n}", "factor": n, "expression": pool[n]} for n in sorted(sampled)]
    dev_tasks, tests = split(items, dev, seed=seed)
    universe = ds.schema["market"]
    if write_data:
        panel, members = market_panel(ds.files["qlib"], universe, start)
        (Path(ws) / "data").mkdir(parents=True, exist_ok=True)
        panel.to_parquet(Path(ws) / "data/market.parquet", index=False)
        members.to_csv(Path(ws) / f"data/{universe}_members.csv", index=False)
    operators, fields = vocabulary(pool.values())
    return {
        "brief": render("alphabench.md", universe=universe, start=start, end=end, n_test=len(tests), n_dev=len(dev_tasks),
                        operators=operators, fields=fields,
                        examples="\n".join(f"- `{pool[n]}`" for n in [n for n in pool if n not in set(sampled)][:3])),
        "tasks": tests, "dev": dev_tasks, "holdout": [], "output": "predictions.jsonl", "modalities": ["table", "timeseries"],
    }
