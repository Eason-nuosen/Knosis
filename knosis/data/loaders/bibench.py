"""BI-Bench：真实 BI 项目上的端到端业务问答。每个用例 = 一组 CSV 表 + 一道业务问题。

    data/bibench/bi-bench/{<用例id>/*.csv, gt/<用例id>[_k].csv, queries.json}
    data/bibench/tools/data_management_tools/metadata/<用例id>/{_tables,_columns,_relationships}.csv
"""

from __future__ import annotations

import json
from pathlib import Path

from ..dataset import Dataset, Task, data_dir
from . import register

METRICS = {"success": "预测结果与任一 GT 表匹配（数值 rtol=1e-2 / atol=0.5，不计行列顺序）的用例比例"}


def scenarios(root: str | Path | None = None) -> list[str]:
    queries = Path(root or data_dir("bibench")) / "bi-bench" / "queries.json"
    return sorted(json.loads(queries.read_text())) if queries.is_file() else []


@register("bibench", scenarios=scenarios)
def load(scenario: str | None = None, root: str | Path | None = None) -> Dataset:
    """`scenario` 是用例 id；也可以是项目 id（如 `280113507`，加载它的全部用例 `280113507-1` …）；
    不给或为 `all` 时加载全部用例。多用例时 files 为空，各用例的表在 `meta["dir"]`。"""
    scenario = None if scenario == "all" else scenario
    base = Path(root or data_dir("bibench"))
    bench, meta = base / "bi-bench", base / "tools" / "data_management_tools"
    queries = json.loads((bench / "queries.json").read_text())
    cases = [scenario] if scenario in queries else sorted(c for c in queries if c.startswith(f"{scenario}-")) if scenario else sorted(queries)
    single = scenario in queries

    tasks = []
    for cid in cases:
        gt = sorted(bench.glob(f"gt/{cid}_*.csv")) or [bench / "gt" / f"{cid}.csv"]  # 多个文件 = 任一匹配即对
        hint = meta / "metadata" / cid / "query_metadata.json"
        tasks.append(Task(
            id=cid,
            input=queries[cid],
            answer=gt,
            kind="bi_query",
            # oracle：该用哪些表 / 做哪些变换，属于提示，不给被测 agent
            meta={"dir": bench / cid, "oracle": json.loads(hint.read_text()) if hint.is_file() else None},
        ))

    files = {}
    if single:
        files = {p.stem: p for p in sorted((bench / scenario).glob("*.csv"))}
        files |= {f"_{k}": meta / "metadata" / scenario / f"_{k}.csv" for k in ("tables", "columns", "relationships")}
        files["_joins"] = meta / "join" / f"{scenario}.csv"
    root_dir = bench / scenario if single else bench
    return Dataset("bibench", scenario or "all", root_dir, files=files, tasks=tasks, metrics=METRICS)
