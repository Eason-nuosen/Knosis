"""SpreadsheetBench：真实论坛问题改写的电子表格操作题，每条指令约 3 个测试用例（OJ 风格）。

    data/spreadsheetbench/all_data_912_v0.1/{dataset.json, spreadsheet/<id>/<n>_<id>_{input,answer}.xlsx}

一道题 = 一条指令；`answer` 是各测试用例的答案文件，`meta.inputs` 是对应的输入文件。
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
    "soft": "各指令测试用例通过率的平均（上游 Soft Restriction）",
    "hard": "指令的全部测试用例都通过才算对（上游 Hard Restriction）",
    "case": "单元格比较：只比 answer_position 内的值（数值保留 2 位小数，日期转 Excel 序列号，空串等于空）",
}


def cases(folder: Path, sid: str) -> list[dict]:
    """一条指令的测试用例：{case, input, answer}，按用例号排序；输入或答案缺失的用例不要。"""
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
        sid = str(item["id"])  # 上游有的 id 是整数
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
