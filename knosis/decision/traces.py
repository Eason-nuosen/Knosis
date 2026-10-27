"""Trace extraction scoring: no tasks, so score the knowledge layer itself: whether it cites steps that exist in the traces, and whether it was re-verified against the environment (`env_verified`) or only checked for consistency with the traces (`trace_checked`)."""

from __future__ import annotations

import re

from ..data.traces import load, parse_ref, refs
from ..knowledge import active, by_unit, load_evidence, load_units, layout
from . import mean, register

STEP = re.compile(r"^data/traces/([^#]+)\.json(#.+)$")
ENV = {"check", "data", "tool", "feedback", "ablation"}


def on_env(entry) -> bool:
    """Whether supporting evidence touches the environment: feedback / ablation come from the environment by nature; others need non-trace data (`data/env/` etc.) among their sources or input dependencies.
    Checks run only on trace files (confirming a claim matches the traces) do not count as environment verification."""
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
