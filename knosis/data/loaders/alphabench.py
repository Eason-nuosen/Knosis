"""AlphaBench: LLM-driven quant factor mining. The repo has only tasks and the factor pool; market data must be downloaded with Qlib.

    data/alphabench/benchmark/data/
      generate/T1_*.json           difficulty -> list of instructions, or records with factor_gt
      generate/tags_system.json    factor tag vocabulary
      evaluate/pool/factor_pool.json   factor name -> expression
      evaluate/raw/{ic,rankic}_table_{csi300,sp500}.csv   daily ground-truth IC (download manually from the links in download.txt)

An evaluate task's answer points to a column of the ground-truth table: `ds.read("ic", usecols=["datetime", answer["column"]])`。
"""

from __future__ import annotations

from pathlib import Path

from ..dataset import Dataset, Task, data_dir, read
from . import register

MARKETS = {"csi300": "cn", "csi500": "cn", "csi1000": "cn", "sp500": "us", "nasdaq100": "us"}

METRICS = {
    "ic": "information coefficient", "rankic": "rank IC", "icir": "IC mean / std", "annualized_return": "annualized return",
    "ndcg_at_k": "evaluate tasks NDCG@K", "precision_at_k": "evaluate tasks Precision@K", "mae": "evaluate tasks MAE", "rmse": "evaluate tasks RMSE",
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
    """`scenario` is generate / evaluate; omitted loads both."""
    base = Path(root or data_dir("alphabench"))
    bdata = base / "benchmark" / "data"
    files = {
        "tags": bdata / "generate" / "tags_system.json",
        "factor_pool": bdata / "evaluate" / "pool" / "factor_pool.json",
        "alpha158": base / "factors" / "lib" / "alpha158",
        "qlib": Path(qlib_dir or base / "qlib_data" / f"{MARKETS[market]}_data").expanduser(),
        "ic": bdata / "evaluate" / "raw" / f"ic_table_{market}.csv",          # rows = trading days, columns = factor names
        "rankic": bdata / "evaluate" / "raw" / f"rankic_table_{market}.csv",  # only csi300 / sp500 exist
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
