"""Convert a workspace or knowledge base in an older layout to the current one (`kb/` + `evidence/`), see `layout`.

    knosis migrate <workspace or knowledge base> [...]

Older layout: a workspace's knowledge layer is in `knowledge/`; a knowledge base is itself the knowledge layer directory (`units.jsonl`, `evidence.jsonl` ... at the root).
What is converted:
- Moves: units.jsonl / ontology/ -> kb/knowledge/, skills/, outline.yaml -> kb/, evidence.jsonl -> evidence/ledger.jsonl,
  checks/, feedback/, traces/ -> evidence/; per-stage knowledge snapshots of a workspace (`stages/**/knowledge/`) are converted too.
- Renames: scope utility -> usage (id prefix `utility/` -> `usage/`), form method -> procedure;
  paths `knowledge/{checks,traces,feedback,ontology}/` -> new locations (rewritten in units, evidence, outline, skills, check scripts, used_units).
- Evidence on skills (unit `skill:<name>`) becomes a usage unit (`usage/skill:<name>/migrated`, `meta.of` pointing to the skill) and is reattached to it.
Workspaces get `AGENTS.md` rewritten from the new template, and each commits a git version.

Traces: old step sequences `<id>.jsonl` under `traces/` (one `{step, role, kind, text}` per line) become ATIF traces `<id>.json` + `.md`
(see `knosis.data.traces`); references `traces/<id>.jsonl#step/<n>` are rewritten to the new step numbers (old steps merged into one ATIF step point to it);
`BRIEF.md` of trace workspaces is rewritten in the new format. Workspaces or knowledge bases already on the current layout get only this step.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ..data.traces import detect, dump, legacy, read, render
from ..lang import t
from .layout import CHECKS, FEEDBACK, LEDGER, ONTOLOGY, OUTLINE, SKILLS, TRACES, UNITS, ensure
from .units import load_units, write_units

MOVES = {"units.jsonl": UNITS, "ontology": ONTOLOGY, "skills": SKILLS, "outline.yaml": OUTLINE,
         "outline.draft.yaml": "kb/outline.draft.yaml", "evidence.jsonl": LEDGER, "checks": CHECKS,
         "feedback": FEEDBACK, "traces": TRACES, "organize.log": "kb/consolidate.log"}
PATHS = {"checks": CHECKS, "traces": TRACES, "feedback": FEEDBACK, "ontology": ONTOLOGY}


def rewrite_text(text: str) -> str:
    text = re.sub(r"(?<![\w/.])knowledge/(checks|traces|feedback|ontology)(?![\w.-])", lambda m: PATHS[m[1]], text)
    return re.sub(r"(?<![\w/:])utility/", "usage/", text)


def rewrite_unit(unit: dict) -> dict:
    unit = json.loads(rewrite_text(json.dumps(unit, ensure_ascii=False)))
    if unit.get("scope") == "utility":
        unit["scope"] = "usage"
    if unit.get("form") == "method":
        unit["form"] = "procedure"
    return unit


def convert(old: Path, root: Path) -> dict:
    """Move the old knowledge layer directory `old` into `root` (root of the new layout) and rewrite contents. `old` and `root` may be the same (knowledge base)."""
    moved = []
    for name, target in MOVES.items():
        src = old / name
        if src.exists():
            dst = root / target
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and dst.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
                shutil.rmtree(src)
            else:
                shutil.move(str(src), str(dst))
            moved.append(name)
    ensure(root)
    units = [rewrite_unit(u) for u in load_units(root / UNITS)]
    ledger = [json.loads(rewrite_text(json.dumps(e, ensure_ascii=False))) for e in load_units(root / LEDGER)]
    # evidence on skills -> usage units
    by_skill = {}
    for e in ledger:
        if str(e.get("unit", "")).startswith("skill:"):
            by_skill.setdefault(e["unit"], []).append(e)
    for sid, entries in by_skill.items():
        uid = f"usage/{sid}/migrated"
        supports = [e for e in entries if e["verdict"] == "support"]
        decisive = [e for e in entries if e["verdict"] in {"support", "refute"}]
        verified = any(e["method"] in {"feedback", "ablation"} for e in supports)
        status = "contested" if decisive and decisive[-1]["verdict"] == "refute" else ("verified" if verified else "inferred")
        sources = list(dict.fromkeys(e["source"] for e in entries))
        units.append({"id": uid, "content": t(f"Effect record of {sid} (migrated from the {len(entries)} evidence entries kept on the skill: "
                                              f"{len(supports)} support, {len(decisive) - len(supports)} refute).",
                                              f"{sid} 的效果记录（迁移自旧布局记在 skill 上的 {len(entries)} 条证据："
                                              f"支持 {len(supports)}，反驳 {len(decisive) - len(supports)}）。"),
                      "form": "fact", "scope": "usage", "provenance": " ; ".join(sources), "status": status,
                      "condition": t("migrated from an older layout; see each evidence entry for question types and samples",
                                     "由旧布局迁移；具体题型与样本见各条证据"), "meta": {"of": sid, "migrated": True}})
        for e in entries:
            e["unit"] = uid
    write_units(root / UNITS, units)
    write_units(root / LEDGER, ledger)
    for path in [root / OUTLINE, root / "kb/outline.draft.yaml", *(root / SKILLS).glob("*/SKILL.md"),
                 *(root / CHECKS).rglob("*.py"), *(root / FEEDBACK).glob("*.json")]:
        if path.exists():
            path.write_text(rewrite_text(path.read_text(encoding="utf-8")), encoding="utf-8")
    shutil.rmtree(root / CHECKS / "__pycache__", ignore_errors=True)
    if old != root and old.exists():
        leftover = [p for p in old.iterdir() if p.name != "__pycache__"]
        for p in leftover:
            shutil.move(str(p), str(root / "kb" / p.name))
        shutil.rmtree(old, ignore_errors=True)
    return {"moved": moved, "units": len(units), "evidence": len(ledger), "skill_evidence": len(by_skill)}


LEGACY_REF = re.compile(r"((?:data|evidence)/traces/)([^#;\s\"'`]+?)\.jsonl(?:#step/(\d+))?")
TEXT = {".jsonl", ".json", ".yaml", ".md", ".py", ".txt"}


def files(root, skip=("data", ".git", ".knosis")):
    for p in root.rglob("*"):
        rel = p.relative_to(root).parts
        if p.is_file() and rel[0] not in skip and "__pycache__" not in rel:
            yield p


def upgrade_traces(root: Path) -> dict:
    """Old step sequences -> ATIF, rewriting all references (units, evidence, outline, skills, check scripts, feedback, used_units, including stage snapshots)."""
    mappings = {}
    found = [p for p in [*(root / "data/traces").glob("*.jsonl"), *(p for p in files(root) if p.parent.name == "traces"
                                                                      and p.suffix == ".jsonl")]]
    for path in found:
        rows = read(path)
        if not rows or detect(rows) != "legacy":
            continue
        t, mapping = legacy(rows, path.name)
        mappings.setdefault(path.stem, mapping)
        out = dump(t, path.with_suffix(".json"))
        out.with_suffix(".md").write_text(render(t, path.stem), encoding="utf-8")
        path.unlink()
    if not mappings:
        return {"traces": 0}

    def sub(m):
        name, n = m[2], m[3]
        if name not in mappings:
            return m[0]
        return f"{m[1]}{name}.json" + (f"#step/{mappings[name].get(int(n), int(n))}" if n is not None else "")

    rewritten = 0
    for path in files(root):
        if path.suffix not in TEXT or path.parent.name == "traces":
            continue
        text = path.read_text(encoding="utf-8")
        new = LEGACY_REF.sub(sub, text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            rewritten += 1
    state = root / ".knosis/state.json"
    if state.exists() and json.loads(state.read_text(encoding="utf-8")).get("benchmark") == "traces":
        from ..data.traces import load
        from ..workspace.exporters.traces import brief, describe

        scenario = json.loads(state.read_text(encoding="utf-8"))["scenario"]
        lines = [describe(p.stem, load(p)) for p in sorted((root / "data/traces").glob("*.json"))]
        env = root / "data/env"
        n_env = sum(1 for p in env.rglob("*") if p.is_file()) if env.is_dir() else None
        (root / "BRIEF.md").write_text(brief(scenario, lines, n_env), encoding="utf-8")
    return {"traces": len(mappings), "files_rewritten": rewritten}


def fresh_inputs(root: Path) -> set:
    """(evidence id, fingerprint) pairs still valid before migration. Migration only moves files, rewrites paths or re-encodes traces without changing content:
    afterwards these fingerprints are replaced with the new files' so the evidence is not judged expired; evidence already expired stays expired."""
    from .evidence import fingerprint

    out = set()
    for ledger in (p for p in files(root) if p.name in ("ledger.jsonl", "evidence.jsonl")):
        for e in load_units(ledger):
            for key, value in e.get("inputs", {}).items():
                if (root / key).is_file() and fingerprint(root / key) == value:
                    out.add((e.get("id"), value))
    return out


def refresh_inputs(root: Path, fresh: set) -> int:
    from .evidence import fingerprint

    n = 0
    for ledger in (p for p in files(root) if p.name == "ledger.jsonl"):
        entries, changed = load_units(ledger), False
        for e in entries:
            for key, value in e.get("inputs", {}).items():
                if (e.get("id"), value) in fresh and (root / key).is_file() and fingerprint(root / key) != value:
                    e["inputs"][key], changed, n = fingerprint(root / key), True, n + 1
        if changed:
            write_units(ledger, entries)
    return n


def commit(path, message) -> None:
    if (path / ".git").exists():
        subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=Knosis", "-c", "user.email=knosis@localhost", "commit", "--quiet",
                        "--allow-empty", "-m", message], cwd=path, check=True, capture_output=True)


def migrate(path) -> dict:
    from string import Template

    path = Path(path).resolve()
    report, messages = None, []
    fresh = fresh_inputs(path)
    if (path / "kb").is_dir():
        pass
    elif (path / ".knosis/state.json").exists() and (path / "knowledge").is_dir():
        report = {"path": str(path), "kind": "workspace", "current": convert(path / "knowledge", path), "snapshots": 0}
        for old in sorted(path.glob("stages/**/knowledge")):
            if (old / "units.jsonl").exists():
                convert(old, old.parent)
                report["snapshots"] += 1
        for used in path.glob("stages/**/*used_units.jsonl"):
            used.write_text(rewrite_text(used.read_text(encoding="utf-8")), encoding="utf-8")
        from ..workspace import templates

        (path / "AGENTS.md").write_text(Template((templates() / "AGENTS.md").read_text(encoding="utf-8")).substitute(
            python=sys.executable), encoding="utf-8")
        messages.append("migrate to the current layout (kb/ + evidence/)")
    elif (path / "units.jsonl").exists():
        report = {"path": str(path), "kind": "kb", "current": convert(path, path)}
        gitignore = path / ".gitignore"
        if gitignore.exists():
            gitignore.write_text(gitignore.read_text(encoding="utf-8").replace("outline.draft.yaml", "kb/outline.draft.yaml"),
                                 encoding="utf-8")
        messages.append("migrate to the current layout (kb/ + evidence/)")
    else:
        raise ValueError(f"{path}: not a workspace or knowledge base in an older layout")
    traces = upgrade_traces(path)
    if traces["traces"]:
        messages.append(f"convert {traces['traces']} traces to ATIF v1.7")
    if not messages:
        return {"path": str(path), "skipped": "already current"}
    report = (report or {"path": str(path), "kind": "workspace" if (path / ".knosis/state.json").exists() else "kb"}) | {"traces": traces}
    report["fingerprints_refreshed"] = refresh_inputs(path, fresh)
    commit(path, "; ".join(messages))
    return report
