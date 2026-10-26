"""Who&When：每条失败日志转成 ATIF 轨迹放进 `data/traces/<id>.json`（另有 `.md`），标注留在原始目录。

按日志切分 dev 与测试：dev 日志的反馈给出归因对不对（mode=answer 时含标注的 agent、步骤与原因），
测试日志是没见过的日志，检验的是「怎样定位出错的 agent 与步骤」能否迁移，而不是记住某条日志的答案。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ...data.traces import dump, normalize, render as render_trace
from . import register, render, split


@register("whoandwhen")
def export(ds, ws: Path, write_data=True, dev=10, limit=30, seed=0, answer=False, **opts) -> dict:
    """`answer`：题目里给出任务的标准答案（上游 with ground truth 设置）；默认不给。"""
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
