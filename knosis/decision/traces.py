"""轨迹提取打分：没有题目，评知识层本身——是否引用到轨迹里存在的步骤，是否在环境上复核过（`env_verified`），还是只核对了与轨迹一致（`trace_checked`）。"""

from __future__ import annotations

import re

from ..data.traces import load, parse_ref, refs
from ..knowledge import active, by_unit, load_evidence, load_units, layout
from . import mean, register

STEP = re.compile(r"^data/traces/([^#]+)\.json(#.+)$")
ENV = {"check", "data", "tool", "feedback", "ablation"}


def on_env(entry) -> bool:
    """支持证据是否触及环境：反馈 / 消融本身来自环境；其余要求来源或依赖的输入里有轨迹以外的数据（`data/env/` 等）。
    只在轨迹文件上跑的检查（核对说法与轨迹一致）不算环境复核。"""
    if entry["verdict"] != "support" or entry["method"] not in ENV:
        return False
    if entry["method"] in ("feedback", "ablation"):
        return True
    paths = [s.strip().split("#")[0] for s in entry["source"].split(";")] + list(entry.get("inputs", {}))
    return any(p.startswith("data/") and not p.startswith("data/traces/") for p in paths)


@register("traces")
def score(ws, state, ds, path, ids) -> dict:
    steps = {f.stem: refs(load(f)) for f in (ws / "data/traces").glob("*.json")}
    evidence = by_unit(load_evidence(ws), ws)
    items = []
    for unit in active(load_units(layout(ws).units)):
        found = [m for m in (STEP.match(s.strip()) for s in unit["provenance"].split(";")) if m]
        valid = [m for m in found if m.group(1) in steps and parse_ref(m.group(2)) in steps[m.group(1)]]
        verified = any(on_env(e) for e in evidence.get(unit["id"], []))
        checked = any(e["verdict"] == "support" for e in evidence.get(unit["id"], []))
        items.append({"id": unit["id"], "form": unit["form"], "status": unit["status"], "trace_refs": len(found),
                      "valid_refs": len(valid), "cites_trace": bool(found) and len(valid) == len(found),
                      "env_verified": verified, "trace_checked": checked and not verified, "ok": bool(found) and len(valid) == len(found), "gold": None})
    metrics = {"units": len(items), "cites_trace": mean(items, "cites_trace"), "env_verified": mean(items, "env_verified"),
               "trace_checked": mean(items, "trace_checked"),
               "traces": len(steps), "steps": sum(len(v) for v in steps.values())}
    return {"metrics": metrics, "items": items, "reference": {}}
