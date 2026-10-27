"""Who&When: failure attribution on failure logs of LLM multi-agent systems (which agent, at which step, caused the failure), hand-annotated by the paper authors.

    data/whoandwhen/Who&When/{Algorithm-Generated,Hand-Crafted}/<n>.json

One task = one failure log; `answer` is the annotation {agent, step, reason}, with `step` converted to the ATIF step number (upstream `mistake_step` is a history index, +1).
The trace itself is converted by `knosis.data.traces.whoandwhen`; annotations and the task's reference answer stay out of the trace.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..dataset import Dataset, Task, data_dir
from ..traces import speaker
from . import register

SUBSETS = {"algorithm": ("Algorithm-Generated", "ag"), "hand": ("Hand-Crafted", "hc")}
SCENARIOS = ("all", *SUBSETS)
METRICS = {
    "agent": "fraction with the faulty agent correct (upstream agent-level accuracy; names case-insensitive)",
    "step": "fraction with the decisive error step correct (upstream step-level accuracy)",
    "both": "fraction with both agent and step correct",
}


@register("whoandwhen", scenarios=SCENARIOS)
def load(scenario: str = "all", root: str | Path | None = None) -> Dataset:
    base = Path(root or data_dir("whoandwhen"))
    tasks, files = [], {}
    for key, (folder, prefix) in SUBSETS.items():
        if scenario not in ("all", key):
            continue
        for path in sorted((base / "Who&When" / folder).glob("*.json"), key=lambda p: int(p.stem)):
            run = json.loads(path.read_text(encoding="utf-8"))
            tid = f"{prefix}-{path.stem}"
            files[tid] = path
            tasks.append(Task(
                id=tid, input=run["question"], kind=key,
                answer={"agent": run["mistake_agent"], "step": int(run["mistake_step"]) + 1, "reason": run["mistake_reason"]},
                meta={"file": path, "n_steps": len(run["history"]), "level": run.get("level"),
                      "agents": sorted({speaker(e) for e in run["history"]} - {None}),
                      "reference_answer": run.get("ground_truth", run.get("groundtruth"))},
            ))
    return Dataset("whoandwhen", scenario, base, files=files, tasks=tasks, metrics=METRICS)
