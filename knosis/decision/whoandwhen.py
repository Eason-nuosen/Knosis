"""Who&When scoring: upstream agent-level and step-level accuracy.

Deliverable `predictions.jsonl`, one `{"id": log id, "answer": {"agent": "<faulty agent>", "step": <ATIF step no>, "reason": "..."}}` per line.
Agent names are compared with parenthetical notes removed and case ignored (upstream has `Websurfer` vs `WebSurfer`); the step number is compared with the annotated `mistake_step + 1`.
Reference: expected accuracy of randomly guessing one agent and one step.
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
                      "gold": f"faulty agent {gold['agent']}, step {gold['step']}: {gold['reason']}"})
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
