"""Who&When 打分：上游的 agent-level 与 step-level accuracy。

交付 `predictions.jsonl`，每行 `{"id": 日志 id, "answer": {"agent": "<出错 agent>", "step": <ATIF 步号>, "reason": "..."}}`。
agent 名去掉括号说明、忽略大小写比较（上游有 `Websurfer` 对 `WebSurfer`）；步号与标注的 `mistake_step + 1` 比较。
参照：随机猜一个 agent、一个步骤的期望准确率。
"""

from __future__ import annotations

from ..data.traces import PAREN
from . import answers, mean, register


def norm(name) -> str:
    return PAREN.sub("", str(name or "")).strip().lower()


def step_of(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@register("whoandwhen")
def score(ws, state, ds, path, ids) -> dict:
    from pathlib import Path

    tasks = {t.id: t for t in ds.tasks}
    preds = answers(path) if path and Path(path).exists() else {}
    items = []
    for tid in ids:
        task, pred = tasks[tid], preds.get(tid)
        pred = pred if isinstance(pred, dict) else {}
        gold = task.answer
        agent_ok = bool(pred.get("agent")) and norm(pred["agent"]) == norm(gold["agent"])
        step_ok = step_of(pred.get("step")) == gold["step"]
        items.append({"id": tid, "kind": task.kind, "agent_ok": agent_ok, "step_ok": step_ok, "ok": agent_ok and step_ok,
                      "predicted": {"agent": pred.get("agent"), "step": pred.get("step")},
                      "gold": f"出错 agent {gold['agent']}，步骤 {gold['step']}：{gold['reason']}"})
    by_kind = {}
    for kind in ("algorithm", "hand"):
        rows = [r for r in items if r["kind"] == kind]
        if rows:
            by_kind[kind] = {"n": len(rows), "agent": mean(rows, "agent_ok"), "step": mean(rows, "step_ok")}
    chosen = [tasks[t] for t in ids]
    return {"metrics": {"agent": mean(items, "agent_ok"), "step": mean(items, "step_ok"), "both": mean(items, "ok"),
                        "missing": sum(t not in preds for t in ids), "by_kind": by_kind},
            "items": items,
            "reference": {"random": {"agent": sum(1 / max(1, len(t.meta["agents"])) for t in chosen) / max(1, len(chosen)),
                                     "step": sum(1 / t.meta["n_steps"] for t in chosen) / max(1, len(chosen))}}}
