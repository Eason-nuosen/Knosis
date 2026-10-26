"""Who&When：LLM 多 agent 系统失败日志的失败归因（哪个 agent、在哪一步造成了失败），标注由论文作者人工完成。

    data/whoandwhen/Who&When/{Algorithm-Generated,Hand-Crafted}/<n>.json

一道题 = 一条失败日志；`answer` 是标注 {agent, step, reason}，`step` 换成 ATIF 步号（上游 `mistake_step` 是 history 下标，+1）。
轨迹本身由 `knosis.data.traces.whoandwhen` 转换，标注与题目标准答案不进轨迹。
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
    "agent": "出错 agent 判对的比例（上游 agent-level accuracy；名字忽略大小写）",
    "step": "决定性出错步骤判对的比例（上游 step-level accuracy）",
    "both": "agent 与步骤都判对的比例",
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
