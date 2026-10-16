"""AlphaBench：LLM 挖掘量化因子。仓库只有任务与因子池，行情要自己用 Qlib 下载。

    data/alphabench/benchmark/data/
      generate/T1_*.json           难度 -> 指令列表，或带 factor_gt 的记录列表
      generate/tags_system.json    因子标签词表
      evaluate/pool/factor_pool.json   因子名 -> 表达式
      evaluate/raw/{ic,rankic}_table_{csi300,sp500}.csv   每日 IC 真值（需从 download.txt 的外链手动下载）

evaluate 题的 answer 指向真值表里的一列：`ds.read("ic", usecols=["datetime", answer["column"]])`。
"""

from __future__ import annotations

from pathlib import Path

from ..dataset import Dataset, Task, data_dir, read
from . import register

MARKETS = {"csi300": "cn", "csi500": "cn", "csi1000": "cn", "sp500": "us", "nasdaq100": "us"}

METRICS = {
    "ic": "信息系数", "rankic": "排序 IC", "icir": "IC 均值 / 标准差", "annualized_return": "年化收益",
    "ndcg_at_k": "评估任务 NDCG@K", "precision_at_k": "评估任务 Precision@K", "mae": "评估任务 MAE", "rmse": "评估任务 RMSE",
}


def _generate_tasks(path: Path) -> list[Task]:
    data = read(path)
    groups = {"": data} if isinstance(data, list) else {k: v for k, v in data.items() if isinstance(v, list)}
    tasks = []
    for level, items in groups.items():
        for i, item in enumerate(items):
            if isinstance(item, str):
                q, a, meta = item, None, {}
            elif isinstance(item, dict):
                meta = dict(item)
                q = meta.get("base_prompt") or meta.get("prompt") or meta.get("instruction") or meta.get("query", "")
                a = meta.pop("factor_gt", meta.pop("answer", None))
            else:
                continue
            tasks.append(Task(id=f"generate/{path.stem}/{level or 'all'}/{i}", input=q, answer=a,
                              kind=path.stem, meta={"difficulty": level, **meta}))
    return tasks


@register("alphabench", scenarios=("generate", "evaluate"))
def load(scenario: str | None = None, root: str | Path | None = None, market: str = "csi300",
         qlib_dir: str | Path | None = None) -> Dataset:
    """`scenario` 为 generate / evaluate，不给就两者都加载。"""
    base = Path(root or data_dir("alphabench"))
    bdata = base / "benchmark" / "data"
    files = {
        "tags": bdata / "generate" / "tags_system.json",
        "factor_pool": bdata / "evaluate" / "pool" / "factor_pool.json",
        "alpha158": base / "factors" / "lib" / "alpha158",
        "qlib": Path(qlib_dir or base / "qlib_data" / f"{MARKETS[market]}_data").expanduser(),
        "ic": bdata / "evaluate" / "raw" / f"ic_table_{market}.csv",          # 行 = 交易日，列 = 因子名
        "rankic": bdata / "evaluate" / "raw" / f"rankic_table_{market}.csv",  # 只有 csi300 / sp500 两份
    }

    tasks = []
    if scenario in (None, "generate"):
        for f in sorted((bdata / "generate").glob("T*.json")):
            tasks += _generate_tasks(f)
    if scenario in (None, "evaluate") and files["factor_pool"].is_file():
        with_gt = set(files["ic"].open().readline().strip().split(",")[1:]) if files["ic"].is_file() else set()
        tasks += [
            Task(id=f"evaluate/{name}", input=expr, kind="evaluate",
                 answer={"ic": files["ic"], "rankic": files["rankic"], "column": name} if name in with_gt else None)
            for name, expr in read(files["factor_pool"]).items()
        ]

    return Dataset("alphabench", scenario or "all", base, files=files,
                   schema={"market": market, "region": MARKETS[market]}, tasks=tasks, metrics=METRICS)
