"""KramaBench: end-to-end data lake → insight pipelines. Files are deliberately not listed; finding them is part of the task.

    data/kramabench/{workload/<domain>.json, data/<domain>/input/, solutions/<domain>/<task id>.py}
"""

from __future__ import annotations

import json
from pathlib import Path

from ..dataset import Dataset, Task, data_dir
from . import register

DOMAINS = ("archeology", "astronomy", "biomedical", "environment", "legal", "wildfire")

METRICS = {
    "answer": "metric by answer_type: exact → success, approximate → MAE/RAE or LLM-judged equivalence, list → F1",
    "pipeline_design": "pipeline design score (llm_code_eval)",
    "pipeline_implementation": "pipeline implementation score (llm_code_eval)",
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
            meta={**t, "solution": files["solutions"] / f"{t['id']}.py"},  # subtasks are here too
        )
        for t in json.loads(files["workload"].read_text())
    ]
    return Dataset("kramabench", scenario, base, files=files, tasks=tasks, metrics=METRICS)
