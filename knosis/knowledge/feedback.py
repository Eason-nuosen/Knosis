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
    used = path.with_name(f"{path.stem}_used_units.jsonl")
    if used.exists():
        utility(ws, record, load_units(used), {t["id"]: t.get("kind", "all") for t in load_units(ws / "tasks/dev.jsonl")})
    return record


def utility(ws, record, used, kinds) -> None:
    """效用知识（scope=utility）：按题型统计每条知识「用到时 / 没用到时」的 dev 正确率，写成候选 κ 与 feedback 证据。

    `used`：与提交文件同名的 `<文件名>_used_units.jsonl`，每行 `{id, used_units}`。只用 dev 反馈，不碰测试题。
    """
    from .evidence import add_evidence
    from .units import write_units

    ok = {item["id"]: bool(item.get("ok")) for item in record["items"]}
    cited = {row["id"]: set(row.get("used_units", [])) for row in used if row["id"] in ok}
    from .skills import load_skills, skill_id

    units = load_units(ws / "knowledge/units.jsonl")
    known = {u["id"] for u in units} | {skill_id(s) for s in load_skills(ws / "knowledge")}
    stats = {}
    for tid, refs in cited.items():
        for uid in refs & known:
            stats.setdefault((uid, kinds.get(tid, "all")), []).append(ok[tid])
    fresh, evidence = {}, []
    for (uid, kind), hits in stats.items():
        others = [ok[t] for t in cited if kinds.get(t, "all") == kind and uid not in cited[t]]
        rate = sum(hits) / len(hits)
        base = sum(others) / len(others) if others else None
        content = (f"在 {kind} 类 dev 题上，用到 {uid} 的 {len(hits)} 题答对 {sum(hits)} 题（{rate:.0%}）；"
                   + (f"没用到的 {len(others)} 题答对率 {base:.0%}。" if others else "同类题都用到了它。"))
        unit_id = f"utility/{uid}/{kind}"
        fresh[unit_id] = {"id": unit_id, "content": content, "form": "fact", "scope": "utility",
                          "condition": f"统计自反馈记录 {record['id']}，样本小，相关不等于因果；可用 ws fork --drop 做消融",
                          "provenance": f"feedback:{record['id']}", "status": "inferred",
                          "derived_from": [] if uid.startswith("skill:") else [uid],
                          "meta": {"of": uid, "kind": kind, "n_used": len(hits), "acc_used": rate, "n_other": len(others), "acc_other": base}}
        if base is not None and rate != base:
            evidence.append({"unit": unit_id, "verdict": "support" if rate > base else "refute", "method": "feedback",
                             "source": f"feedback:{record['id']}", "note": content})
    if fresh:
        write_units(ws / "knowledge/units.jsonl", [u for u in units if u["id"] not in fresh] + list(fresh.values()))
        add_evidence(ws / "knowledge", evidence)
