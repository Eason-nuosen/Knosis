"""SpreadsheetBench: the agent gets the input spreadsheets of all test cases for each instruction and returns the modified ones; answer spreadsheets stay in the raw directory.

Dev and test are split by instruction: dev feedback gives the first mismatching cell per case (with the correct value when mode=answer);
test instructions are unseen, so the test checks whether "how to do this kind of operation" transfers rather than memorizing a sheet.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from . import place, register, render, split


def usable(task, xlsm) -> bool:
    """By default only take instructions with all 3 cases present and all .xlsx (.xlsm has macros; openpyxl reads values only and saving may drop macros)."""
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
