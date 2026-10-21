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


def select_skills(directory, text=None, include_inactive=False) -> list[dict]:
    """列出 skill（解题集），附其效果证据计数；`text` 在 name / description / when 里找子串。"""
    from .skills import load_skills, skill_id

    evidence = by_unit(load_evidence(directory))
    out = []
    for skill in load_skills(directory):
        if not include_inactive and skill.get("status", "active") != "active":
            continue
        blob = " ".join(str(skill.get(k, "")) for k in ("name", "description", "when")).lower()
        if text and text.lower() not in blob:
            continue
        counts = {}
        for entry in evidence.get(skill_id(skill), []):
            counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1
        out.append({k: skill.get(k) for k in ("name", "description", "when", "uses", "status", "path")} | {"evidence": counts})
    return out


def anchors(unit) -> list[str]:
    """一条知识锚定的对象：来源里的数据位置与 `about`（本体元素名或数据位置）。"""
    sources = [s.strip() for s in unit.get("provenance", "").split(";")]
    return sorted({s for s in sources if s.startswith("data/")} | set(unit.get("about", [])))


def index(directory, ws=None, prefix=None) -> dict[str, dict]:
    """以对象为键的视图：{对象: {"units": [κ id], "used_in": {κ id: 被决策引用的次数}}}。

    `prefix`：只看以它开头的对象（如 `data/train.parquet#col/`）；`ws`：给定时统计各 decide / dev 交付旁的
    `used_units` 里每条知识被引用的次数。对象既可以是文件（`data/x.csv`），也可以是其中的位置（`#col/…`、`#node/…`）。
    """
    from . import all_ontology_units, ontology_docs

    directory = Path(directory)
    units = load_units(directory / "units.jsonl") + all_ontology_units(ontology_docs(directory))
    used = {}
    if ws is not None:
        for path in Path(ws).glob("stages/**/*used_units.jsonl"):
            for row in load_units(path):
                for uid in row.get("used_units", []):
                    used[uid] = used.get(uid, 0) + 1
    view = {}
    for unit in units:
        for anchor in anchors(unit):
            for key in {anchor, anchor.split("#", 1)[0]}:
                if prefix and not key.startswith(prefix):
                    continue
                entry = view.setdefault(key, {"units": [], "used_in": {}})
                if unit["id"] not in entry["units"]:
                    entry["units"].append(unit["id"])
                if used.get(unit["id"]):
                    entry["used_in"][unit["id"]] = used[unit["id"]]
    return dict(sorted(view.items()))
