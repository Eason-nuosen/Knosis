"""Select knowledge for a task: correct knowledge is not necessarily useful for the task at hand; the agent decides what to pick, this only filters and counts evidence."""

from __future__ import annotations

from pathlib import Path

from .evidence import by_unit, load_evidence
from .layout import layout
from .units import INACTIVE, load_units


def select(base, about=(), form=None, text=None, include_inactive=False, ontology=True, root=None,
           include_contested=False) -> list[dict]:
    """Return candidate units (κ and ontology view units), each with `evidence: {support, refute, undetermined, not_applicable}`.

    `about`: ontology element name, matching a κ's `about` or the ontology unit itself; `text`: case-insensitive substring in id / content / condition.
    Contested units are excluded unless `include_contested` or `include_inactive` is set.
    """
    from . import all_ontology_units, ontology_docs

    units = load_units(layout(base).units)
    units += all_ontology_units(ontology_docs(base)) if ontology else []
    evidence = by_unit(load_evidence(base), root)
    chosen = []
    for unit in units:
        if not include_inactive and unit["status"] in INACTIVE:
            continue
        if not (include_contested or include_inactive) and unit["status"] == "contested":
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


def select_skills(base, text=None, include_inactive=False) -> list[dict]:
    """List skills (solution playbooks) with the usage units that evaluate them (`meta.of` pointing to them) and their status; `text` is a substring in name / description / when."""
    from .skills import load_skills, skill_id

    usage = [u for u in load_units(layout(base).units) if u.get("scope") == "usage" and u["status"] not in INACTIVE]
    out = []
    for skill in load_skills(base):
        if not include_inactive and skill.get("status", "active") != "active":
            continue
        blob = " ".join(str(skill.get(k, "")) for k in ("name", "description", "when")).lower()
        if text and text.lower() not in blob:
            continue
        rated = [{"id": u["id"], "status": u["status"], "content": u["content"]} for u in usage
                 if u.get("meta", {}).get("of") == skill_id(skill)]
        out.append({k: skill.get(k) for k in ("name", "description", "when", "uses", "status", "path")} | {"usage": rated})
    return out


def anchors(unit) -> list[str]:
    """Objects a knowledge unit is anchored to: data locations in its provenance and `about` (ontology element names or data locations)."""
    sources = [s.strip() for s in unit.get("provenance", "").split(";")]
    return sorted({s for s in sources if s.startswith("data/")} | set(unit.get("about", [])))


def index(base, ws=None, prefix=None) -> dict[str, dict]:
    """Object-keyed view: {object: {"units": [κ id], "used_in": {κ id: times cited by decisions}}}.

    `prefix`: only objects starting with it (e.g. `data/train.parquet#col/`); `ws`: if given, count how often each unit is cited in the
    `used_units` next to each decide / dev deliverable. An object can be a file (`data/x.csv`) or a location in it (`#col/…`, `#node/…`).
    """
    from . import all_ontology_units, ontology_docs

    units = load_units(layout(base).units) + all_ontology_units(ontology_docs(base))
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
