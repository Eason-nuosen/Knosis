"""Who&When: each failure log becomes an ATIF trace in `data/traces/<id>.json` (plus `.md`); annotations stay in the raw directory.

Dev and test are split by log: dev feedback says whether the attribution is correct (with the annotated agent, step and reason when mode=answer);
test logs are unseen, so the test checks whether "how to locate the failing agent and step" transfers rather than memorizing a log's answer.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ...data.traces import dump, normalize, render as render_trace
from . import register, render, split


@register("whoandwhen")
def export(ds, ws: Path, write_data=True, dev=10, limit=30, seed=0, answer=False, **opts) -> dict:
    """`answer`: include the task's reference answer in each question (upstream with-ground-truth setting); off by default."""
    answer = str(answer).lower() in ("1", "true", "yes")
    tasks = []
    for t in ds.tasks:
        task = {"id": t.id, "question": t.input, "trace": f"data/traces/{t.id}.json", "agents": t.meta["agents"],
                "n_steps": t.meta["n_steps"], "system": "Magentic-One（人工搭建）" if t.kind == "hand" else "CaptainAgent（自动生成）"}
        if answer:
            task["reference_answer"] = t.meta["reference_answer"]
        tasks.append(task)
    dev_tasks, tests = split(tasks, dev, limit, seed=seed)
    if write_data:
        for task in dev_tasks + tests:
            t = normalize(ds.files[task["id"]], "whoandwhen")
            out = dump(t, Path(ws) / task["trace"])
            out.with_suffix(".md").write_text(render_trace(t, task["id"]), encoding="utf-8")
    kinds = Counter(task["id"].split("-")[0] for task in dev_tasks + tests)
    return {
        "brief": render("whoandwhen.md", scenario=ds.scenario, n_dev=len(dev_tasks), n_test=len(tests),
                        n_hand=kinds.get("hc", 0), n_algorithm=kinds.get("ag", 0),
                        answer_note="题目里给出了任务的标准答案（`reference_answer`）。" if answer
                        else "不提供任务的标准答案：只能从日志本身判断哪里出了错。"),
        "tasks": tests, "dev": dev_tasks, "holdout": [], "output": "predictions.jsonl", "modalities": ["trace"],
    }
