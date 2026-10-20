"""按任务选取知识：知识正确不等于对当前任务有用，选哪些由 agent 决定，这里只提供筛选与证据计数。"""

from __future__ import annotations

from pathlib import Path

from .evidence import by_unit, load_evidence
from .units import INACTIVE, load_units


def select(directory, about=(), form=None, text=None, include_inactive=False, ontology=True, root=None) -> list[dict]:
    """返回候选单元（κ 与本体视图单元），每条附 `evidence: {support, refute, undetermined, not_applicable}`。

    `about`：本体元素名，命中 κ 的 `about` 或本体单元自身；`text`：在 id / content / condition 里找子串（不分大小写）。
    """
    from . import all_ontology_units, ontology_docs

    directory = Path(directory)
    units = load_units(directory / "units.jsonl")
    units += all_ontology_units(ontology_docs(directory)) if ontology else []
    evidence = by_unit(load_evidence(directory), root)
    chosen = []
    for unit in units:
        if not include_inactive and unit["status"] in INACTIVE:
            continue
        if form and unit["form"] != form:
            continue
        names = set(unit.get("about", [])) | {unit["id"].rsplit("/", 1)[-1]}
        if about and not any(a in names or any(n.startswith(a + ".") for n in names) for a in about):
            continue
        blob = " ".join(str(unit.get(k, "")) for k in ("id", "content", "condition")).lower()
        if text and text.lower() not in blob:
            continue
        counts = {}
        for entry in evidence.get(unit["id"], []):
            counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1
        chosen.append({**unit, "evidence": counts})
    return chosen
