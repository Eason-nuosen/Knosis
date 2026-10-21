"""反馈子层：agent 在 dev 题上的提交结果，记录在 `knowledge/feedback/<id>.json`。

反馈是 agent 提取知识的依据：例如 NGD-Fin 上 dev 题答错、而按观测图执行无误，说明相关的边或属性有噪声，
agent 把它写成 finding / fact，provenance 写 `feedback:<id>#item/<题目 id>`。
dev 题与测试题不重叠，GT 从原始数据目录读，不进工作区（mode=answer 时随反馈给出 dev 题的正确答案）。
`mode=score` 只返回对错与分数，`mode=answer` 另给出正确答案，`mode=none` 关闭；`budget` 限制提交次数。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .units import load_units


def records(ws) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(ws) / "knowledge/feedback").glob("*.json"))]


def own(ws) -> list[dict]:
    """本工作区自己提交的记录（从知识库继承来的记录名为 `<工作区>.<id>`，不计入预算）。"""
    return [r for r in records(ws) if "." not in r["id"]]


def left(ws, state) -> int:
    config = state["feedback"]
    return 0 if config["mode"] == "none" else config["budget"] - len(own(ws))


def submit(ws, path) -> dict:
    """在 dev GT 上给 `path`（与 decide 交付同格式，只含 dev 题，可以只交一部分）打分，写一条反馈记录并返回它。"""
    from ..decision import SCORERS
    from ..workspace import open_dataset, prediction_ids, status

    ws, path = Path(ws).resolve(), Path(path).resolve()
    state = status(ws)
    if left(ws, state) <= 0:
        raise RuntimeError(f"feedback unavailable (mode={state['feedback']['mode']}, budget={state['feedback']['budget']})")
    dev = {task["id"] for task in load_units(ws / "tasks/dev.jsonl")}
    ids, _ = prediction_ids(path)
    if set(ids) - dev:
        raise ValueError(f"feedback only accepts dev ids; unknown: {sorted(set(ids) - dev, key=str)[:10]}")
    if state["feedback"].get("full") and dev - set(ids):
        raise ValueError(f"this workspace requires answering all dev tasks; missing: {sorted(dev - set(ids), key=str)[:10]}")
    ds = open_dataset(state["benchmark"], state["scenario"], state["options"])
    result = SCORERS[state["benchmark"]](ws, state, ds, path, ids)
    items = result["items"] if state["feedback"]["mode"] == "answer" else [
        {k: v for k, v in item.items() if k != "gold"} for item in result["items"]]
    directory = ws / "knowledge/feedback"
    directory.mkdir(parents=True, exist_ok=True)
    name = state["stage"] + (f"-r{state['round']}" if state["stage"] == "refine" else "")
    record = {"id": f"{len(own(ws)) + 1:03d}-{name}", "stage": state["stage"], "round": state["round"],
              "benchmark": state["benchmark"], "scenario": state["scenario"],
              "submitted": str(path.relative_to(ws)), "mode": state["feedback"]["mode"],
              "created": datetime.now(timezone.utc).isoformat(), "metrics": result["metrics"], "items": items}
    (directory / f"{record['id']}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return record
