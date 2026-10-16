"""KramaBench：数据湖 → 洞察的端到端流水线。刻意不列文件清单，找文件是题目的一部分。

    data/kramabench/{workload/<域>.json, data/<域>/input/, solutions/<域>/<任务 id>.py}
"""

from __future__ import annotations

import json
from pathlib import Path

from ..dataset import Dataset, Task, data_dir
from . import register

DOMAINS = ("archeology", "astronomy", "biomedical", "environment", "legal", "wildfire")

METRICS = {
    "answer": "按 answer_type 选指标：exact → success，approximate → MAE/RAE 或 LLM 判同义，list → F1",
    "pipeline_design": "流水线设计分（llm_code_eval）",
    "pipeline_implementation": "流水线实现分（llm_code_eval）",
}


@register("kramabench", scenarios=DOMAINS)
def load(scenario: str = "wildfire", root: str | Path | None = None) -> Dataset:
    base = Path(root or data_dir("kramabench"))
    files = {
        "lake": base / "data" / scenario / "input",
        "workload": base / "workload" / f"{scenario}.json",
        "solutions": base / "solutions" / scenario,
    }
    tasks = [
        Task(
            id=t["id"],
            input=t.pop("query"),
            answer=t.pop("answer", None),
            kind=t.get("answer_type", ""),
            meta={**t, "solution": files["solutions"] / f"{t['id']}.py"},  # subtasks 也在这里
        )
        for t in json.loads(files["workload"].read_text())
    ]
    return Dataset("kramabench", scenario, base, files=files, tasks=tasks, metrics=METRICS)
