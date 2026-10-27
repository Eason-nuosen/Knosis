"""Dev feedback: results of agent submissions on dev questions, recorded in `evidence/feedback/<id>.json`.

Feedback is a basis for extracting knowledge: e.g. on NGD-Fin, a wrong dev answer despite correct execution on the observed graph
means the related edges or attributes are noisy; the agent writes it as a finding / fact with provenance `feedback:<id>#item/<question id>`.
Dev and test questions do not overlap; GT is read from the raw data directory and never enters the workspace (mode=answer returns dev answers with the feedback).
`mode=score` returns only correctness and score, `mode=answer` also returns the correct answers, `mode=none` disables it; `budget` caps submissions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .layout import layout
from .units import load_units


def records(ws) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(layout(ws).feedback.glob("*.json"))]


def own(ws) -> list[dict]:
    """Records submitted by this workspace (records inherited from the knowledge base are named `<workspace>.<id>` and do not count toward the budget)."""
    return [r for r in records(ws) if "." not in r["id"]]


def left(ws, state) -> int:
    config = state["feedback"]
    return 0 if config["mode"] == "none" else config["budget"] - len(own(ws))


def submit(ws, path) -> dict:
    """Score `path` (same format as the decide deliverable, dev questions only, may be partial) against dev GT; write and return a feedback record."""
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
    directory = layout(ws).feedback
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
        usage(ws, record, load_units(used), {t["id"]: t.get("kind", "all") for t in load_units(ws / "tasks/dev.jsonl")})
    return record


def usage(ws, record, used, kinds) -> None:
    """Usage knowledge (scope=usage): per question type, dev accuracy of each knowledge unit / skill when used vs. not used, written as candidate κ and feedback evidence.

    `used`: `<file name>_used_units.jsonl` next to the submission, one `{id, used_units}` per line. Uses dev feedback only, never test questions.
    """
    from .evidence import add_evidence
    from .units import write_units

    ok = {item["id"]: bool(item.get("ok")) for item in record["items"]}
    cited = {row["id"]: set(row.get("used_units", [])) for row in used if row["id"] in ok}
    from .skills import load_skills, skill_id

    units = load_units(layout(ws).units)
    known = {u["id"] for u in units} | {skill_id(s) for s in load_skills(ws)}
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
        unit_id = f"usage/{uid}/{kind}"
        fresh[unit_id] = {"id": unit_id, "content": content, "form": "fact", "scope": "usage",
                          "condition": f"统计自反馈记录 {record['id']}，样本小，相关不等于因果；可用 ws fork --drop 做消融",
                          "provenance": f"feedback:{record['id']}", "status": "inferred",
                          "derived_from": [] if uid.startswith("skill:") else [uid],
                          "meta": {"of": uid, "kind": kind, "n_used": len(hits), "acc_used": rate, "n_other": len(others), "acc_other": base}}
        if base is not None and rate != base:
            evidence.append({"unit": unit_id, "verdict": "support" if rate > base else "refute", "method": "feedback",
                             "source": f"feedback:{record['id']}", "note": content})
    if fresh:
        write_units(layout(ws).units, [u for u in units if u["id"] not in fresh] + list(fresh.values()))
        add_evidence(ws, evidence)
