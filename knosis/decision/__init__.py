"""Decision layer: how decide outputs are scored, and how knowledge is used in decisions.

One scorer per dataset, `score(ws, state, ds, path, ids) -> dict`, registered with `@register("<dataset>")`:
`path` is the deliverable (format: see the exporter's `output`), `ids` are the task ids to score, `ds` is reloaded from the raw data directory (with GT).
Returns `{"metrics": {...}, "items": [{"id", "ok", "gold", ...}], "reference": {...}}`:
`evaluate` calls it on test tasks; dev feedback (`knowledge.feedback.submit`) calls the same function on dev tasks.

Whether the knowledge itself is correct (separately from whether it helps the task) is scored by the optional `score_knowledge(ws, state, ds) -> dict`,
registered with `@register_knowledge("<dataset>")`; results go into the `knowledge` section of the eval report. It may read GT, but results are never returned to the agent.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Callable

from ..knowledge import INACTIVE, all_ontology_units, layout, load_units, ontology_docs, skills

SCORERS: dict[str, Callable] = {}
KNOWLEDGE_SCORERS: dict[str, Callable] = {}


def register(name: str):
    def deco(fn):
        SCORERS[name] = fn
        return fn

    return deco


def register_knowledge(name: str):
    def deco(fn):
        KNOWLEDGE_SCORERS[name] = fn
        return fn

    return deco


def evaluate(ws, write: bool = True) -> dict:
    from ..workspace import open_dataset, status

    # In driver mode the agent runs with KNOSIS_DEPTH=1: hide test scores from it, otherwise it would be tuning against GT.
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("evaluation is disabled inside agent runs (KNOSIS_DEPTH >= 1)")
    ws = Path(ws).resolve()
    state = status(ws)
    ds = open_dataset(state["benchmark"], state["scenario"], state["options"])
    ids = [task["id"] for task in load_units(ws / "tasks/tasks.jsonl")] if state["output"] else []
    path = ws / "stages/4_decide" / state["output"] if state["output"] else None
    result = SCORERS[state["benchmark"]](ws, state, ds, path, ids)
    report = {"benchmark": state["benchmark"], "scenario": state["scenario"],
              "knowledge": state.get("knowledge", "K_final"), "n": len(ids), **result["metrics"],
              "reference": result.get("reference", {}), "usage": usage(ws)}
    report["knowledge_summary"] = summary(ws)
    if state["benchmark"] in KNOWLEDGE_SCORERS:
        report["knowledge"] = KNOWLEDGE_SCORERS[state["benchmark"]](ws, state, ds)
    report["usage_effect"] = test_usage(ws, result["items"])
    if write:
        (ws / ".knosis/eval.json").write_text(
            json.dumps({**report, "items": result["items"]}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return report


def usage(ws) -> dict:
    """How knowledge is cited in `stages/4_decide/used_units.jsonl` (one {id, used_units} per line)."""
    path = Path(ws) / "stages/4_decide/used_units.jsonl"
    units = {u["id"]: u for u in load_units(layout(ws).units)}
    if not path.exists():
        return {"reported": False, "units": len(units)}
    rows = load_units(path)
    cited = [uid for row in rows for uid in row.get("used_units", [])]
    # Ontology units and skills can be cited too.
    known = set(units) | {u["id"] for u in all_ontology_units(ontology_docs(ws))}
    known |= {skills.skill_id(s) for s in skills.load_skills(ws)}
    return {
        "reported": True, "units": len(units), "predictions": len(rows),
        "with_knowledge": sum(bool(row.get("used_units")) for row in rows) / max(1, len(rows)),
        "distinct_units_used": len(set(cited) & known),
        "unknown_units": sorted(set(cited) - known),
        "inactive_units": sorted({uid for uid in cited if units.get(uid, {}).get("status") in INACTIVE}),
    }


def test_usage(ws, items) -> dict:
    """Effect of each cited unit on test tasks: accuracy when used vs. not used. Written only to the eval report, never back to the knowledge layer (otherwise test results would leak through the knowledge base)."""
    path = Path(ws) / "stages/4_decide/used_units.jsonl"
    if not path.exists() or not items or "ok" not in items[0]:
        return {"reported": False}
    ok = {str(i["id"]): bool(i["ok"]) for i in items}
    cited = {str(r["id"]): set(r.get("used_units", [])) for r in load_units(path) if str(r["id"]) in ok}
    rows = []
    for uid in sorted(set().union(*cited.values())) if cited else []:
        hit = [ok[t] for t in cited if uid in cited[t]]
        other = [ok[t] for t in cited if uid not in cited[t]]
        rows.append({"unit": uid, "n_used": len(hit), "acc_used": mean_bool(hit),
                     "n_other": len(other), "acc_other": mean_bool(other)})
    return {"reported": True, "units": sorted(rows, key=lambda r: -r["n_used"])}


def mean_bool(values):
    return sum(values) / len(values) if values else None


def summary(ws) -> dict:
    """Knowledge layer overview: unit counts by form / status, evidence counts by verdict, number of units with executable checks."""
    from ..knowledge import load_evidence

    units = load_units(layout(ws).units)
    count = lambda values: dict(sorted(Counter(values).items()))  # noqa: E731
    from ..knowledge import scope_of

    return {"units": len(units), "scopes": count(scope_of(u) for u in units),
            "levels": count("meta" if scope_of(u) in ("method", "usage") else "object" for u in units),
            "forms": count(u["form"] for u in units), "statuses": count(u["status"] for u in units),
            "with_check": sum("check" in u for u in units),
            "evidence": count(e["verdict"] for e in load_evidence(ws)),
            "consolidate": count(a["op"] for a in load_units(layout(ws).actions)) if layout(ws).actions.exists() else {}}


def answers(path) -> dict:
    """JSONL deliverable -> {id: answer}."""
    return {row["id"]: row.get("answer") for row in load_units(path)}


def mean(rows, key) -> float:
    return sum(r[key] for r in rows) / max(1, len(rows))


from . import (  # noqa: E402,F401
    alphabench, bibench, burr, graph_qa, kramabench, llm_srbench, newtonbench, relbench, spreadsheetbench, tabular, text,
    traces, whoandwhen,
)
