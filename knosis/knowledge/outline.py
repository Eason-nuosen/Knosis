"""知识体系（大纲）：把零散的单跳知识（κ / skill）串成层级脉络，`kb/outline.yaml`。

大纲只是导航层，不新增断言：每节的 summary 只概括成员单元已经说了的内容，对错仍以单元及其证据为准；
因此改大纲不需要证据，也不改 `units.jsonl`。

    title: NewtonBench 万有引力族
    summary: ……
    sections:
      - id: scene                 # 全大纲唯一
        title: 场景：从实验数据发现幂律
        summary: 一两句，说这一节的知识讲什么、对哪类任务有用
        units: [extract/single-axis-scaling, skill:discover-positive-power]   # κ、本体单元或 skill:<名字>
        notes: 可选，疑似重复 / 互相矛盾的单元等，留给人看（字符串或字符串列表）
        sections: [...]           # 子节
      - id: archive
        title: 已撤回或失效
        archive: true             # 只有 archive 节可以放 retracted / stale 的单元

默认层级（`draft` 生成，由 agent 改写成有语义的分组）：场景（usage 与 skill）→ 方法（method）
→ 数据间关系（relation）→ 数据整体规律（dataset）→ 具体对象（instance），后三层按锚定的数据文件分组。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .layout import layout
from .units import INACTIVE, SCOPES, load_units, scope_of

FILE = "outline.yaml"
LAYERS = {
    "usage": ("scene", "场景：哪些知识对哪类任务有用"),
    "method": ("method", "方法：如何发现与验证知识"),
    "relation": ("relation", "数据间关系"),
    "dataset": ("dataset", "数据整体规律"),
    "instance": ("instance", "具体对象"),
}


def load_outline(base) -> dict | None:
    path = layout(base).outline
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


def write_outline(base, outline, name=FILE) -> Path:
    path = layout(base).kb / name
    path.write_text(yaml.safe_dump(outline, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    return path


def walk(sections, depth=0):
    for section in sections or []:
        yield depth, section
        yield from walk(section.get("sections"), depth + 1)


def members(base) -> dict[str, dict]:
    """可以放进大纲的条目：κ、本体单元、skill（记为 `skill:<名字>`），{id: 条目}。"""
    from . import all_ontology_units, ontology_docs
    from .skills import load_skills, skill_id

    path = layout(base).units
    items = {u["id"]: u for u in (load_units(path) if path.exists() else [])}
    items |= {u["id"]: u for u in all_ontology_units(ontology_docs(base))}
    for skill in load_skills(base):
        items[skill_id(skill)] = {"id": skill_id(skill), "content": skill.get("description", ""), "form": "skill",
                                  "status": skill.get("status", "active"), "scope": "usage", "uses": skill.get("uses", [])}
    return items


def inactive(item) -> bool:
    return item.get("status") in INACTIVE or item.get("status") == "retracted"


def anchor_file(item) -> str:
    from .select import anchors

    files = sorted({a.split("#", 1)[0] for a in anchors(item) if a.startswith("data/")})
    return files[0] if files else ""


def draft(base, title=None) -> dict:
    """按粒度与锚定文件生成的大纲草稿；本体单元很多时不逐个列，只在「数据间关系」下记一节。"""
    items = members(base)
    groups: dict[str, dict[str, list]] = {scope: {} for scope in SCOPES}
    archived = []
    for uid, item in items.items():
        if inactive(item):
            archived.append(uid)
            continue
        if uid.startswith("ontology/"):
            groups["relation"].setdefault("本体", []).append(uid)
            continue
        scope = item.get("scope") or scope_of(item)
        key = "" if scope in ("usage", "method") else anchor_file(item)
        groups[scope].setdefault(key, []).append(uid)
    sections = []
    for scope, (sid, name) in LAYERS.items():
        by_file = groups[scope]
        if not by_file:
            continue
        section = {"id": sid, "title": name, "summary": "", "units": by_file.pop("", [])}
        children = [{"id": f"{sid}/{i + 1}", "title": key or "未锚定到数据文件", "summary": "", "units": ids}
                    for i, (key, ids) in enumerate(sorted(by_file.items()))]
        if children:
            section["sections"] = children
        sections.append(section)
    if archived:
        sections.append({"id": "archive", "title": "已撤回或失效", "archive": True, "units": sorted(archived)})
    return {"title": title or Path(base).resolve().name, "summary": "", "sections": sections}


def check_outline(outline, items: dict) -> list[str]:
    """结构问题：节缺 id / title、id 重复、引用未知条目、活跃区放了失效单元；不要求覆盖全部单元（见 `unplaced`）。"""
    if not isinstance(outline, dict) or not outline.get("title"):
        return ["outline: missing title"]
    issues, seen = [], set()
    for _, section in walk(outline.get("sections")):
        sid = section.get("id")
        if not sid or not section.get("title"):
            issues.append(f"outline section {sid or '?'}: missing id or title")
        if sid in seen:
            issues.append(f"outline section {sid}: duplicate id")
        seen.add(sid)
        for uid in section.get("units") or []:
            if uid not in items:
                issues.append(f"outline section {sid}: unknown unit {uid}")
            elif inactive(items[uid]) and not section.get("archive"):
                issues.append(f"outline section {sid}: inactive unit {uid} must move to an archive section")
    return issues


def placed(outline) -> set[str]:
    return {uid for _, s in walk((outline or {}).get("sections")) for uid in s.get("units") or []}


def unplaced(outline, items: dict) -> list[str]:
    """还没放进大纲的活跃条目（新加的知识要补进去）。"""
    have = placed(outline)
    return sorted(uid for uid, item in items.items() if uid not in have and not inactive(item)
                  and not uid.startswith("ontology/"))


def render(outline, items: dict, evidence=None) -> str:
    """markdown：节标题 + 摘要 + 成员（id、状态、粒度、内容摘录、证据计数）。"""
    evidence = evidence or {}
    lines = [f"# {outline['title']}", ""]
    if outline.get("summary"):
        lines += [outline["summary"], ""]
    for depth, section in walk(outline.get("sections")):
        lines += [f"{'#' * min(depth + 2, 6)} {section['title']}  `{section['id']}`", ""]
        if section.get("summary"):
            lines += [section["summary"], ""]
        for uid in section.get("units") or []:
            item = items.get(uid, {"content": "（未知单元）", "status": "?"})
            counts = {}
            for entry in evidence.get(uid, []):
                counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1
            text = item.get("content", "")
            text = text if len(text) <= 120 else text[:120] + " …"
            ev = "，".join(f"{k} {v}" for k, v in counts.items())
            lines.append(f"- `{uid}` [{item.get('scope') or scope_of(item)}/{item.get('status')}] {text}" + (f"（{ev}）" if ev else ""))
        notes = section.get("notes")
        if notes:
            lines += ["", *[f"> {note}" for note in (notes if isinstance(notes, list) else str(notes).splitlines())]]
        lines.append("")
    left = unplaced(outline, items)
    if left:
        lines += [f"## 未归类（{len(left)}）", "", *[f"- `{uid}` {items[uid].get('content', '')[:80]}" for uid in left], ""]
    return "\n".join(lines)
