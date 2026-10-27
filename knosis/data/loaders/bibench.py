"""BI-Bench: end-to-end business QA on real BI projects. Each case = a set of CSV tables + one business question.

    data/bibench/bi-bench/{<case id>/*.csv, gt/<case id>[_k].csv, queries.json}
    data/bibench/tools/data_management_tools/metadata/<case id>/{_tables,_columns,_relationships}.csv
"""

from __future__ import annotations

import json
from pathlib import Path

from ..dataset import Dataset, Task, data_dir
from . import register

METRICS = {"success": "fraction of cases whose prediction matches any GT table (numbers rtol=1e-2 / atol=0.5, row and column order ignored)"}


def scenarios(root: str | Path | None = None) -> list[str]:
    queries = Path(root or data_dir("bibench")) / "bi-bench" / "queries.json"
    return sorted(json.loads(queries.read_text())) if queries.is_file() else []


@register("bibench", scenarios=scenarios)
def load(scenario: str | None = None, root: str | Path | None = None) -> Dataset:
    """`scenario` is a case id, or a project id (e.g. `280113507` loads all its cases `280113507-1` …);
    omitted or `all` loads every case. With multiple cases `files` is empty and each case's tables are in `meta["dir"]`."""
    scenario = None if scenario == "all" else scenario
    base = Path(root or data_dir("bibench"))
    bench, meta = base / "bi-bench", base / "tools" / "data_management_tools"
    queries = json.loads((bench / "queries.json").read_text())
    cases = [scenario] if scenario in queries else sorted(c for c in queries if c.startswith(f"{scenario}-")) if scenario else sorted(queries)
    single = scenario in queries

    tasks = []
    for cid in cases:
        gt = sorted(bench.glob(f"gt/{cid}_*.csv")) or [bench / "gt" / f"{cid}.csv"]  # multiple files = matching any one is correct
        hint = meta / "metadata" / cid / "query_metadata.json"
        tasks.append(Task(
            id=cid,
            input=queries[cid],
            answer=gt,
            kind="bi_query",
            # oracle: which tables / transforms to use; these are hints, not given to the agent under test
            meta={"dir": bench / cid, "oracle": json.loads(hint.read_text()) if hint.is_file() else None},
        ))

    files = {}
    if single:
        files = {p.stem: p for p in sorted((bench / scenario).glob("*.csv"))}
        files |= {f"_{k}": meta / "metadata" / scenario / f"_{k}.csv" for k in ("tables", "columns", "relationships")}
        files["_joins"] = meta / "join" / f"{scenario}.csv"
    root_dir = bench / scenario if single else bench
    return Dataset("bibench", scenario or "all", root_dir, files=files, tasks=tasks, metrics=METRICS)
