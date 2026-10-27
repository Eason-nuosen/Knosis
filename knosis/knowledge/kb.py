"""Standalone knowledge base (KB): a knowledge layer accumulated across workspaces; itself a git repository, one commit per write-back.

    <kb>/
    ├── kb/  evidence/    same layout as a workspace, see `layout`
    └── IMPORT.md         import log (e.g. stats of GT stripped from ontologies)

A workspace inherits from it via `ws init --kb` (`inherit`) and writes back with `merge` when done; `check_knowledge` runs before write-back and failures are rejected.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from .evidence import data_inputs, load_evidence, run_check
from .layout import CHECKS, FEEDBACK, ONTOLOGY, SKILLS, TRACES, ensure, layout
from .units import load_units, scope_of, write_units

# Directories copied along with κ, and which scopes must be inherited to copy them (None means always).
PARTS = {ONTOLOGY: {"relation", "dataset"}, SKILLS: {"skill", "usage"}, CHECKS: None, FEEDBACK: None, TRACES: None}
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def git(kb, *args) -> str:
    return subprocess.run(["git", *args], cwd=kb, check=True, capture_output=True, text=True).stdout.strip()


def commit(kb, message) -> str:
    git(kb, "add", "-A")
    git(kb, "-c", "user.name=Knosis", "-c", "user.email=knosis@localhost", "commit", "--quiet", "--allow-empty", "-m", message)
    return git(kb, "rev-parse", "--short", "HEAD")


def init_kb(kb) -> Path:
    kb = Path(kb).resolve()
    kb.mkdir(parents=True, exist_ok=False)
    ensure(kb)
    # agent logs and outline drafts from collect / consolidate are not versioned
    (kb / ".gitignore").write_text("*.log\nkb/outline.draft.yaml\n__pycache__/\n", encoding="utf-8")
    git(kb, "init", "--quiet")
    commit(kb, "init")
    return kb


def inherit(kb, target, scopes=None) -> dict:
    """Copy the current KB version to `target` (workspace root or snapshot directory); if `scopes` is given, inherit only κ of those scopes (e.g. only
    method meta-knowledge, or both method,usage). Ontologies belong to relation / dataset and skills to `skill` or `usage`; they are copied only with those scopes."""
    kb, target = Path(kb).resolve(), Path(target)
    units = load_units(layout(kb).units)
    scopes = list(scopes) if scopes else None
    if scopes:
        kept = {u["id"] for u in units if scope_of(u) in scopes}
        # On partial inheritance, dropped parents no longer resolve; record the derivation in meta.
        units = [{**u, "derived_from": [p for p in u.get("derived_from", []) if p in kept],
                  "meta": {**u.get("meta", {}), "inherited_derived_from": u.get("derived_from", [])}}
                 for u in units if u["id"] in kept]
    version = git(kb, "rev-parse", "--short", "HEAD")
    # Mark as from the knowledge base: its `data/` sources point to the environment that produced it, see `source_issues`.
    units = [{**u, "meta": {**u.get("meta", {}), "inherited": u.get("meta", {}).get("inherited", version)}} for u in units]
    ids = {u["id"] for u in units}
    write_units(layout(target).units, units)
    write_units(layout(target).ledger, [{**e, "inherited": e.get("inherited", version)} for e in load_evidence(kb)
                                        if e["unit"] in ids or not scopes])
    for part, wanted in PARTS.items():
        if (kb / part).is_dir() and (not scopes or not wanted or wanted & set(scopes)):
            shutil.copytree(kb / part, target / part, dirs_exist_ok=True, ignore=IGNORE)
    # The knowledge graph and flowcharts reference units of the whole KB: copy them only on full inheritance; otherwise the new workspace's structure step rebuilds them.
    if not scopes:
        if (kb / "kb/graph.json").exists():
            shutil.copy2(kb / "kb/graph.json", target / "kb/graph.json")
        if (kb / "kb/flows").is_dir():
            shutil.copytree(kb / "kb/flows", target / "kb/flows", dirs_exist_ok=True)
    return {"path": str(kb), "version": version, "scopes": scopes, "units": len(units)}


def seen_items(kb, benchmark, scenario) -> set:
    """Question ids seen in the KB's feedback records for the same dataset: test questions of a new workspace must exclude them (mode=answer feedback carries the correct answers)."""
    records = [json.loads(p.read_text(encoding="utf-8")) for p in layout(kb).feedback.glob("*.json")]
    return {item["id"] for r in records if (r.get("benchmark"), r.get("scenario")) == (benchmark, scenario)
            for item in r["items"]}


def portable(ws, unit) -> tuple[bool, str]:
    """Run the unit's check in a temporary workspace containing only `data/`, `kb/` and `evidence/`; only a result matching the in-place run shows it does not depend on other files of this workspace."""
    here = run_check(unit, ws)[0]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "data").symlink_to(Path(ws).resolve() / "data")
        for part in ("kb", "evidence"):
            shutil.copytree(Path(ws) / part, tmp / part, ignore=IGNORE)
        verdict, note = run_check(unit, tmp)
    return verdict == here and "Traceback" not in note, note


def namespaced(unit, rename) -> dict:
    """Rewrite every field of the unit that points to other units using `rename` (old id -> new id)."""
    unit = {**unit, "id": rename(unit["id"])}
    for key in ("derived_from", "conflicts_with"):
        if unit.get(key):
            unit[key] = [rename(x) for x in unit[key]]
    for key in ("merged_into", "superseded_by"):
        if unit.get(key):
            unit[key] = rename(unit[key])
    if isinstance(unit.get("meta"), dict) and unit["meta"].get("of"):
        unit["meta"] = {**unit["meta"], "of": rename(unit["meta"]["of"])}
    if isinstance(unit.get("check"), dict) and str(unit["check"].get("path", "")).startswith(CHECKS + "/"):
        unit["check"] = {**unit["check"], "path": unit["check"]["path"].replace(CHECKS + "/", f"{CHECKS}/{rename.ns}/", 1)}
    return unit


def merge(ws, kb, namespace=None) -> str:
    """Write the workspace's current knowledge layer back to the KB; return the new version number.

    `namespace`: used when merging workspaces of different datasets into one KB. Unit ids get the prefix `<namespace>/`, skills are renamed
    `<namespace>-<name>`, check scripts go to `evidence/checks/<namespace>/`, and all references (derivation, aliases, supersession, conflicts,
    usage targets, evidence, skill uses) are rewritten so same-named ids from different workspaces do not overwrite each other.

    κ are merged by id (the workspace version wins; old versions stay in the KB's git history); unseen evidence is appended;
    feedback records new in the workspace are renamed `<workspace name>.<id>` and sources pointing to them are rewritten;
    referenced traces (`data/traces/<id>.json` and `.md`) are copied into the KB's `evidence/traces/` with sources rewritten to `evidence/traces/...`, so they still resolve after inheritance.
    """
    from . import check_knowledge
    from ..workspace import status

    ws, kb = Path(ws).resolve(), Path(kb).resolve()
    src, dst, state = layout(ws), layout(kb), status(ws)
    renames = {p.stem: f"{ws.name}.{p.stem}" for p in src.feedback.glob("*.json") if "." not in p.stem}

    def rewrite(text):
        text = text.replace("data/traces/", f"{TRACES}/")
        return re.sub(r"feedback:([^#;\s]+)", lambda m: f"feedback:{renames.get(m.group(1), m.group(1))}", text)

    # Executable meta-knowledge must run outside its original workspace; if it fails, record undetermined evidence and write it back to the KB.
    extra = []
    for unit in load_units(src.units):
        if scope_of(unit) == "method" and unit.get("check", {}).get("kind") == "python":
            ok, note = portable(ws, unit)
            if not ok:
                extra.append({"unit": unit["id"], "verdict": "undetermined", "method": "check",
                              "source": f"check:{unit['id']}(portable)", "inputs": data_inputs(ws),
                              "note": f"检查脚本离开原工作区（只保留 data/、kb/ 与 evidence/）运行不通：{note[-200:]}"})
    if extra:
        from .evidence import add_evidence

        add_evidence(ws, extra)
    from ..workspace import snapshots

    def rename(uid):
        if not namespace or uid.startswith("ontology/"):
            return uid
        return f"skill:{namespace}-{uid[6:]}" if uid.startswith("skill:") else f"{namespace}/{uid}"

    rename.ns = namespace
    fix = (lambda u: namespaced(u, rename)) if namespace else (lambda u: u)  # noqa: E731
    units = {u["id"]: u for u in load_units(dst.units)}
    incoming = [fix(json.loads(rewrite(json.dumps(u, ensure_ascii=False)))) for u in load_units(src.units)]
    units |= {u["id"]: u for u in incoming}
    # Units deleted in the workspace but still referenced by derivations are restored into the KB from their last snapshot version, so I1 also holds in the KB.
    history = {u["id"]: u for d in snapshots(ws) for u in (fix(x) for x in load_units(layout(d).units))}
    missing = {p for u in units.values() for p in u.get("derived_from", [])} - set(units)
    units |= {uid: history[uid] for uid in missing if uid in history}
    old = load_evidence(kb)
    key = lambda e: (e["unit"], e["verdict"], e["source"], e["created"])  # noqa: E731
    known = {key(e) for e in old}
    new = [json.loads(rewrite(json.dumps(e, ensure_ascii=False))) for e in load_evidence(ws)]
    new = [{**e, "unit": rename(e["unit"])} for e in new]
    new = [{**e, "id": f"e-{len(old) + i + 1:04d}"} for i, e in enumerate(x for x in new if key(x) not in known)]
    for part in (ONTOLOGY, CHECKS, SKILLS):
        if not (ws / part).is_dir():
            continue
        if namespace and part == CHECKS:
            shutil.copytree(ws / part, kb / part / namespace, dirs_exist_ok=True, ignore=IGNORE)
        elif namespace and part == SKILLS:
            for path in (ws / part).glob("*/SKILL.md"):
                _, head, body = path.read_text(encoding="utf-8").split("---", 2)
                meta = yaml.safe_load(head)
                meta["name"] = f"{namespace}-{meta['name']}"
                meta["uses"] = [rename(x) for x in meta.get("uses", [])]
                out = kb / part / meta["name"]
                shutil.copytree(path.parent, out, dirs_exist_ok=True, ignore=IGNORE)
                (out / "SKILL.md").write_text("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
                                              + "---" + body, encoding="utf-8")
        else:
            shutil.copytree(ws / part, kb / part, dirs_exist_ok=True, ignore=IGNORE)
    text = "".join(p.read_text(encoding="utf-8") for p in (src.units, src.ledger) if p.exists())
    cited = set(re.findall(r"data/traces/([^#;\s\"]+?)\.json", text))
    for name in cited:
        for path in (ws / "data/traces").glob(f"{name}.*"):
            dst.traces.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst.traces / path.name)
    dst.feedback.mkdir(parents=True, exist_ok=True)
    if src.actions.exists():
        with dst.actions.open("a", encoding="utf-8") as fh:
            fh.writelines(json.dumps({**a, "workspace": ws.name} | ({"unit": rename(a["unit"])} if a.get("unit") else {}),
                                     ensure_ascii=False) + "\n" for a in load_units(src.actions))
    for path in src.feedback.glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["id"] = renames.get(path.stem, path.stem)
        record.setdefault("workspace", ws.name)
        record.setdefault("benchmark", state["benchmark"])
        record.setdefault("scenario", state["scenario"])
        (dst.feedback / f"{record['id']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for path in dst.skills.glob("*/SKILL.md"):
        text = path.read_text(encoding="utf-8")
        for before, after in renames.items():
            text = re.sub(rf"(?<![\w.]){re.escape(before)}(?![\w])", after, text)
        path.write_text(text, encoding="utf-8")
    write_units(dst.units, list(units.values()))
    write_units(dst.ledger, old + new)
    if namespace:  # record which workspace the prefix came from: consolidation uses it to find cross-dataset knowledge
        sources = kb / "kb/sources.json"
        known_ns = json.loads(sources.read_text(encoding="utf-8")) if sources.exists() else {}
        known_ns[namespace] = {"workspace": ws.name, "benchmark": state["benchmark"], "scenario": state["scenario"]}
        sources.write_text(json.dumps(known_ns, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    issues = check_knowledge(kb)
    if issues:
        git(kb, "checkout", "--", ".")
        git(kb, "clean", "-fdq")
        raise ValueError("merge rejected:\n" + "\n".join(issues))
    return commit(kb, f"merge {ws.name}: {state['benchmark']}/{state['scenario']}, {len(units)} units, +{len(new)} evidence")


def import_ontology(source, kb, strip=False) -> dict:
    """Import an annotated ontology unit (e.g. ontology-bench annotations) into the KB's `kb/knowledge/ontology/<unit name>/`.

    `strip`: remove parts derived from benchmark GT (Power BI relationships, per-question transformations, etc.), see `ontology.strip_gt`.
    """
    from .ontology import import_annotation

    kb = Path(kb).resolve()
    report = import_annotation(source, layout(kb).ontology, strip=strip)
    with (kb / "IMPORT.md").open("a", encoding="utf-8") as fh:
        fh.write(f"- {Path(source).name}（strip_gt={strip}）：{json.dumps(report, ensure_ascii=False)}\n")
    commit(kb, f"import ontology {Path(source).name} (strip={strip})")
    return report
