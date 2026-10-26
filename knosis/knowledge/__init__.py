"""知识层（v0.5）：两大块，见 `layout`。

    kb/        知识主体：knowledge/{units.jsonl, ontology/}、skills/、outline.yaml
    evidence/  来源与验证：ledger.jsonl、consolidate.jsonl、checks/、feedback/、traces/

κ 单元见 `units`；证据见 `evidence`；本体（OSI 三层，元素也是 κ）见 `ontology`；skill 见 `skills`；
大纲见 `outline`，知识图谱、流程图、派生图与规则卡片见 `structure`；内化（去重、矛盾处理、构建知识体系、结构化）见 `consolidate`；v0.4 旧布局用 `migrate` 转换。
本模块的函数都以 `root`（工作区、知识库或知识版本快照的根目录）为参数。
"""

from pathlib import Path

from . import feedback, outline, skills
from .layout import Layout, data_root, ensure, is_workspace, layout
from .evidence import add_evidence, by_unit, check_evidence, load_evidence, trace, verify
from .ontology import check_ontology, load_ontology, ontology_units, refs, write_ontology
from .units import FORMS, INACTIVE, META, SCOPES, STATUSES, active, check_units, level, load_units, scope_of, write_units

__all__ = [
    "FORMS", "STATUSES", "INACTIVE", "SCOPES", "META", "scope_of", "level", "layout", "Layout", "ensure", "data_root",
    "is_workspace", "load_units", "write_units", "check_units", "active",
    "load_ontology", "write_ontology", "check_ontology", "ontology_units", "refs", "check_knowledge",
    "ontology_docs", "all_ontology_units", "load_evidence", "add_evidence", "check_evidence", "by_unit",
    "verify", "trace",
]


def ontology_docs(base) -> dict[str, dict]:
    """知识库里的全部本体：`kb/knowledge/ontology/` 下直接放的三文件记为 ""，每个含三文件的子目录记为子目录名。"""
    root = layout(base).ontology
    if not root.is_dir():
        return {}
    docs = {"": load_ontology(root)} if any(root.glob("*.yaml")) else {}
    docs |= {sub.name: load_ontology(sub) for sub in sorted(root.iterdir()) if sub.is_dir() and any(sub.glob("*.yaml"))}
    return docs


def all_ontology_units(docs: dict[str, dict]) -> list[dict]:
    units = []
    for name, d in docs.items():
        for unit in ontology_units(d, prefix=str(Path("kb/knowledge/ontology") / name)):
            units.append({**unit, "id": unit["id"].replace("ontology/", f"ontology/{name}/", 1) if name else unit["id"]})
    return units


def check_knowledge(base, known_ids=frozenset(), root=None) -> list[str]:
    """检查一份知识层：κ 结构、状态与证据一致、证据账本、本体跨文件引用、κ 的 `about`、skill、大纲。

    `base`：工作区、知识库或快照的根目录；`root`：工作区目录，给定时检查 `data/` 来源与证据的数据指纹。
    """
    lay = layout(base)
    docs = ontology_docs(base)
    issues = [issue for d in docs.values() for issue in check_ontology(d)]
    names = set().union(*(refs(d) for d in docs.values())) if docs else None
    units = load_units(lay.units) if lay.units.exists() else []
    entries = load_evidence(base)
    issues += check_units(units, known_ids, root, names, evidence=by_unit(entries, root))
    onto = all_ontology_units(docs)
    found = skills.load_skills(base)
    ids = {u["id"] for u in units} | set(known_ids) | {u["id"] for u in onto}
    issues += check_evidence(entries, ids | {skills.skill_id(s) for s in found}, root)
    # skill 讲怎么做、不讲对错：效果写成 usage 单元（meta.of = skill:<名字>），再由证据支持。
    issues += [f"evidence {e['id']}: skill effects are usage units (scope=usage, meta.of={e['unit']}), not evidence on the skill"
               for e in entries if str(e.get("unit", "")).startswith("skill:")]
    records = {p.stem for p in lay.feedback.glob("*.json")}
    # skill 可以引用 κ、本体单元，以及只在历史版本里出现过的 κ（状态未知，不触发失效检查）。
    known = {i: {} for i in known_ids} | {u["id"]: u for u in [*onto, *units]}
    issues += skills.check_skills(found, known, records)
    from .structure import check_structure

    issues += check_structure(base)
    current = outline.load_outline(base)
    if current is not None:
        issues += outline.check_outline(current, outline.members(base))
    return issues
