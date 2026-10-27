"""Knowledge layer: two parts, see `layout`.

    kb/        knowledge body: knowledge/{units.jsonl, ontology/}, skills/, outline.yaml
    evidence/  sources and verification: ledger.jsonl, consolidate.jsonl, checks/, feedback/, traces/

κ units: `units`; evidence: `evidence`; ontology (OSI three layers, elements are also κ): `ontology`; skills: `skills`;
outline: `outline`; knowledge graph, flowcharts, derivation graph and rule cards: `structure`; consolidation (dedup, conflict handling,
organizing, structuring): `consolidate`; older layouts are converted with `migrate`.
All functions here take `root` (root of a workspace, knowledge base or knowledge version snapshot).
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
    """All ontologies in the knowledge base: the three files directly under `kb/knowledge/ontology/` are keyed "", each subdirectory holding the three files is keyed by its name."""
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
    """Check a knowledge layer: κ structure, status/evidence consistency, evidence ledger, ontology cross-file references, κ `about`, skills, outline.

    `base`: root of a workspace, knowledge base or snapshot; `root`: workspace directory; if given, check `data/` sources and evidence data fingerprints.
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
    # A skill says how, not what is true: its effect is a usage unit (meta.of = skill:<name>) backed by evidence.
    issues += [f"evidence {e['id']}: skill effects are usage units (scope=usage, meta.of={e['unit']}), not evidence on the skill"
               for e in entries if str(e.get("unit", "")).startswith("skill:")]
    records = {p.stem for p in lay.feedback.glob("*.json")}
    # A skill may reference κ, ontology units, and κ seen only in history (status unknown, no invalidation check).
    known = {i: {} for i in known_ids} | {u["id"]: u for u in [*onto, *units]}
    issues += skills.check_skills(found, known, records)
    from .structure import check_structure

    issues += check_structure(base)
    current = outline.load_outline(base)
    if current is not None:
        issues += outline.check_outline(current, outline.members(base))
    return issues
