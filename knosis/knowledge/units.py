"""JSONL storage and structural checks for knowledge units κ; only guards structure and status/evidence consistency, never judges content."""

from __future__ import annotations

import json
from pathlib import Path

from .layout import FEEDBACK

# procedure: step-wise expression (e.g. steps for verifying a kind of knowledge), may carry an executable check.
FORMS = {"finding", "fact", "rule", "formula", "schema", "tool", "procedure"}
# contested: refuting evidence exists, unresolved; not selected by default, and users should know it is disputed.
# merged: folded into another unit during dedup (`merged_into`), kept only as an alias; stale: invalid after the environment changed, `superseded_by` may point to the new version.
STATUSES = {"observed", "inferred", "verified", "contested", "retracted", "stale", "merged"}
INACTIVE = {"retracted", "stale", "merged"}
# Scope. Object knowledge (about the environment): instance, a specific object; relation, structure between objects (joins, ontology relations);
# dataset, patterns / distributions / formulas of the data as a whole. Meta-knowledge (about knowledge): method, how knowledge is obtained (discovery and verification);
# usage, how to use knowledge well (which knowledge / skills work for which tasks and readers, backed by feedback or ablation).
# Orthogonal to form (the expression); inferred by `scope_of` when absent.
SCOPES = ("instance", "relation", "dataset", "method", "usage")
META = {"method", "usage"}
POINT = ("#node/", "#edge/", "#row/")
REQUIRED = ("id", "content", "form", "provenance", "status")


def load_units(path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_units(path, units: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        "".join(json.dumps(unit, ensure_ascii=False) + "\n" for unit in units), encoding="utf-8",
    )


def source_issues(source: str, root=None, inherited=False) -> list[str]:
    """Whether a source resolves: a `data/` file exists inside the workspace data directory, a `kb/` / `evidence/` file (e.g. an inherited trace) exists, or a `feedback:` record exists.

    `inherited`: unit / evidence inherited from the knowledge base; its `data/` refers to the environment that produced it, whose layout may differ, so it is not checked.
    """
    if root is None or inherited and source.startswith("data/"):
        return []
    root = Path(root)
    if source.startswith("data/"):
        path = (root / source.split("#", 1)[0]).resolve()
        if not path.is_relative_to(root.resolve() / "data") or not path.exists():
            return [f"missing data source: {source}"]
    if source.startswith(("kb/", "evidence/")) and not (root / source.split("#", 1)[0]).exists():
        return [f"missing source: {source}"]
    if source.startswith("feedback:"):
        record = source.split("#", 1)[0].removeprefix("feedback:")
        if not (root / FEEDBACK / f"{record}.json").exists():
            return [f"missing feedback record: {source}"]
    return []


def scope_of(unit) -> str:
    """Explicit `scope`; otherwise procedure form -> method, join / relational schema -> relation,
    sources all pointing to a single node / edge / row -> instance, everything else -> dataset."""
    if unit.get("scope"):
        return unit["scope"]
    if unit.get("form") == "procedure":
        return "method"
    text = f"{unit.get('id', '')} {unit.get('provenance', '')}"
    if unit.get("form") == "schema" and any(k in text for k in ("join/", "relation/", "relationship/")):
        return "relation"
    sources = [s.strip() for s in unit.get("provenance", "").split(";") if s.strip()]
    if sources and all(any(p in s for p in POINT) for s in sources):
        return "instance"
    return "dataset"


def level(unit) -> str:
    """object (about the environment) or meta (about knowledge)."""
    return "meta" if scope_of(unit) in META else "object"


def resolve(uid, by_id, limit=20):
    """Follow `merged_into` to the unit id an alias ultimately points to."""
    for _ in range(limit):
        target = by_id.get(uid, {}).get("merged_into")
        if not target:
            return uid
        uid = target
    return uid


def check_units(units, known_ids=frozenset(), root: Path | None = None, ontology_refs=None,
                evidence=None) -> list[str]:
    """Return a list of issues; empty = pass.

    `known_ids`: ids seen in historical versions (I1); `root` (workspace): if given, check that `data/` source files and
    `feedback:` records exist;
    `ontology_refs`: if given, check that ontology elements referenced in `about` exist (see `ontology.refs`).
    `evidence`: if given (result of `evidence.by_unit`, unexpired evidence only), check status agrees with evidence:
    verified needs at least one support; if the latest evidence refutes, status must be contested / retracted / stale;
    I2: `support` does not exceed the number of independent sources of supporting evidence (sources deduplicated by the part before `#`).
    """
    issues = []
    by_id = {unit["id"]: unit for unit in units if unit.get("id")}
    available = set(by_id) | set(known_ids)
    seen = set()
    for i, unit in enumerate(units):
        name = unit.get("id") or f"line {i + 1}"
        for key in REQUIRED:
            if not unit.get(key):
                issues.append(f"{name}: missing {key}")
        if name in seen:
            issues.append(f"{name}: duplicate id")
        seen.add(name)
        for key, choices in (("form", FORMS), ("status", STATUSES)):
            if unit.get(key) not in choices:
                issues.append(f"{name}: invalid {key}: {unit.get(key)}")
        if "scope" in unit and unit["scope"] not in SCOPES:
            issues.append(f"{name}: invalid scope: {unit['scope']}")
        parents = unit.get("derived_from", [])
        sources = [s.strip() for s in unit.get("provenance", "").split(";")]
        if "derived" in sources and not parents:
            issues.append(f"{name}: derived provenance requires derived_from")
        inherited = "inherited" in unit.get("meta", {})
        for source in sources:
            issues += [f"{name}: {issue}" for issue in source_issues(source, root, inherited)]
        for parent in parents:
            if parent not in available:
                issues.append(f"{name}: unknown derived_from: {parent}")
            # I5: if a parent is inactive, descendants must be too; a merged parent counts as the unit it was merged into.
            target = by_id.get(resolve(parent, by_id), {})
            if target.get("status") in INACTIVE and unit.get("status") not in INACTIVE:
                issues.append(f"{name}: inactive parent {parent} requires stale or retracted status")
        issues += [f"{name}: {issue}" for issue in consolidation_issues(unit, by_id, available)]
        if evidence is not None:
            issues += [f"{name}: {issue}" for issue in evidence_issues(unit, evidence.get(name, []))]
        if ontology_refs is not None:
            for ref in unit.get("about", []):
                if not ref.startswith("data/") and ref not in ontology_refs:
                    issues.append(f"{name}: unknown ontology ref in about: {ref}")
        # about may also anchor directly to a data location (for object-keyed reverse lookup).
        for ref in unit.get("about", []):
            if ref.startswith("data/"):
                issues += [f"{name}: about {issue}" for issue in source_issues(ref, root, inherited)]
    return issues


def consolidation_issues(unit, by_id, available) -> list[str]:
    """Fields left by consolidation: merged_into (dedup alias), superseded_by (version replacement), conflicts_with (identified conflicts)."""
    issues, status = [], unit.get("status")
    if status == "merged" and not unit.get("merged_into"):
        issues.append("merged requires merged_into")
    if unit.get("merged_into"):
        target = unit["merged_into"]
        if status != "merged":
            issues.append("merged_into requires status merged")
        if target not in by_id:
            issues.append(f"unknown merged_into: {target}")
        elif by_id[resolve(target, by_id)].get("status") in INACTIVE:
            issues.append(f"merged_into {target} must resolve to an active unit")
    if unit.get("superseded_by"):
        if unit["superseded_by"] not in available:
            issues.append(f"unknown superseded_by: {unit['superseded_by']}")
        if status not in {"stale", "retracted"}:
            issues.append("superseded_by requires status stale or retracted")
    for other in unit.get("conflicts_with", []):
        if other not in by_id:
            issues.append(f"unknown conflicts_with: {other}")
        elif status not in INACTIVE and by_id[other].get("status") not in INACTIVE and \
                "contested" not in {status, by_id[other].get("status")}:
            issues.append(f"unresolved conflict with {other}: narrow the conditions and drop conflicts_with, "
                          "retract or supersede one side, or mark it contested")
    return issues


def evidence_issues(unit, entries) -> list[str]:
    supports = [e for e in entries if e["verdict"] == "support"]
    issues = []
    if unit.get("status") == "verified" and not supports:
        issues.append("verified requires at least one unexpired support evidence (knosis knowledge evidence add / verify)")
    decisive = [e for e in entries if e["verdict"] in {"support", "refute"}]
    if decisive and decisive[-1]["verdict"] == "refute" and unit.get("status") not in {"contested", *INACTIVE}:
        issues.append(f"latest evidence {decisive[-1]['id']} refutes it; status must be contested, retracted or stale")
    if scope_of(unit) == "usage" and unit.get("status") == "verified" and not any(
            e["method"] in {"feedback", "ablation"} for e in supports):
        issues.append("usage knowledge can only be verified by feedback or ablation evidence")
    roots = {e["source"].split("#", 1)[0] for e in supports}
    if isinstance(unit.get("support"), int) and unit["support"] > len(roots):
        issues.append(f"I2: support={unit['support']} exceeds {len(roots)} independent supporting sources")
    return issues


def active(units) -> list[dict]:
    """Units usable in the decide stage (including contested; selection excludes them by default, see `select`)."""
    return [unit for unit in units if unit.get("status") not in INACTIVE]
