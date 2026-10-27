"""SpreadsheetBench: spreadsheet manipulation tasks adapted from real forum questions, about 3 test cases per instruction (OJ style).

    data/spreadsheetbench/all_data_912_v0.1/{dataset.json, spreadsheet/<id>/<n>_<id>_{input,answer}.xlsx}

One task = one instruction; `answer` is the answer file of each test case, `meta.inputs` the matching input files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..dataset import Dataset, Task, data_dir
from . import register

SCENARIOS = ("all", "cell", "sheet")
TYPES = {"cell": "Cell-Level Manipulation", "sheet": "Sheet-Level Manipulation"}
METRICS = {
    "soft": "mean per-instruction test case pass rate (upstream Soft Restriction)",
    "hard": "an instruction counts only if all its test cases pass (upstream Hard Restriction)",
    "case": "cell comparison: only values within answer_position (numbers to 2 decimals, dates as Excel serials, empty string equals empty)",
}


def cases(folder: Path, sid: str) -> list[dict]:
    """Test cases of one instruction: {case, input, answer}, sorted by case number; cases missing an input or answer are dropped."""
    found = {}
    for p in folder.iterdir():
        m = re.fullmatch(rf"(\d+)_{re.escape(sid)}_(input|answer)(\.xls[xm])", p.name)
        if m:
            found.setdefault(int(m[1]), {})[m[2]] = p
    return [{"case": n, **v} for n, v in sorted(found.items()) if {"input", "answer"} <= set(v)]


@register("spreadsheetbench", scenarios=SCENARIOS)
def load(scenario: str = "all", root: str | Path | None = None, version: str = "all_data_912_v0.1") -> Dataset:
    base = Path(root or data_dir("spreadsheetbench")) / version
    items = json.loads((base / "dataset.json").read_text(encoding="utf-8"))
    tasks = []
    for item in items:
        if scenario in TYPES and item["instruction_type"] != TYPES[scenario]:
            continue
        sid = str(item["id"])  # some upstream ids are integers
        found = cases(base / item["spreadsheet_path"], sid)
        tasks.append(Task(
            id=sid, input=item["instruction"], answer=[c["answer"] for c in found],
            kind="cell" if item["instruction_type"].startswith("Cell") else "sheet",
            meta={"inputs": [c["input"] for c in found], "cases": [c["case"] for c in found],
                  "answer_position": item["answer_position"], "answer_sheet": item.get("answer_sheet"),
                  "data_position": item.get("data_position"), "instruction_type": item["instruction_type"]},
        ))
    return Dataset("spreadsheetbench", scenario, base, files={"dataset": base / "dataset.json"}, tasks=tasks,
                   metrics=METRICS)
