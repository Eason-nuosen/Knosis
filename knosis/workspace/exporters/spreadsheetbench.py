"""SpreadsheetBench：agent 拿到每条指令全部测试用例的输入表格，交回改好的表格；答案表格留在原始目录。

按指令切分 dev 与测试：dev 指令的反馈带每个用例第一处不一致的单元格（mode=answer 时含正确值），
测试指令是没见过的指令，检验的是「这类操作怎么做」能否迁移，而不是记住某张表。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from . import place, register, render, split


def usable(task, xlsm) -> bool:
    """默认只取 3 个用例齐全、都是 .xlsx 的指令（.xlsm 带宏，openpyxl 只能读值、保存可能丢宏）。"""
    files = task.meta["inputs"] + task.answer
    return len(task.answer) == 3 and (xlsm or all(p.suffix == ".xlsx" for p in files))


@register("spreadsheetbench")
def export(ds, ws: Path, write_data=True, dev=5, limit=15, seed=0, xlsm=False, **opts) -> dict:
    pool = [t for t in ds.tasks if usable(t, xlsm)]
    tasks = []
    for t in pool:
        inputs = [f"data/{t.id}/{n}_input{p.suffix}" for n, p in zip(t.meta["cases"], t.meta["inputs"])]
        tasks.append({"id": t.id, "instruction": t.input, "instruction_type": t.meta["instruction_type"],
                      "answer_position": t.meta["answer_position"], "inputs": inputs})
    dev_tasks, tests = split(tasks, dev, limit, seed=seed)
    chosen = {t["id"] for t in dev_tasks + tests}
    if write_data:
        for t in pool:
            if t.id in chosen:
                for n, p in zip(t.meta["cases"], t.meta["inputs"]):
                    place(p, Path(ws) / "data" / t.id / f"{n}_input{p.suffix}")
    kinds = Counter(t["instruction_type"].split("-")[0] for t in dev_tasks + tests)
    return {
        "brief": render("spreadsheetbench.md", scenario=ds.scenario, n_dev=len(dev_tasks), n_test=len(tests),
                        n_cell=kinds.get("Cell", 0), n_sheet=kinds.get("Sheet", 0)),
        "tasks": tests, "dev": dev_tasks, "holdout": [], "output": "predictions.jsonl", "modalities": ["spreadsheet"],
    }
