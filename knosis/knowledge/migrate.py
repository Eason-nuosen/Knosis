"""把 v0.4 布局的工作区或知识库转换为 v0.5（`kb/` + `evidence/`），见 `layout`。

    knosis migrate <工作区或知识库> [...]

v0.4：工作区的知识层在 `knowledge/`，知识库本身就是知识层目录（根目录下 `units.jsonl`、`evidence.jsonl` ……）。
转换内容：
- 文件搬家：units.jsonl / ontology/ → kb/knowledge/，skills/、outline.yaml → kb/，evidence.jsonl → evidence/ledger.jsonl，
  checks/、feedback/、traces/ → evidence/；工作区各阶段的知识快照（`stages/**/knowledge/`）同样转换。
- 改名：scope utility → usage（id 前缀 `utility/` → `usage/`），form method → procedure；
  路径 `knowledge/{checks,traces,feedback,ontology}/` → 新位置（单元、证据、大纲、skill、检查脚本、used_units 里都改）。
- skill 上的证据（unit 为 `skill:<名字>`）转成一条 usage 单元（`usage/skill:<名字>/migrated`，`meta.of` 指向 skill），证据改挂到它上面。
工作区会按新模板重写 `AGENTS.md`，并各自提交一个 git 版本。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

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
    """把旧知识层目录 `old` 的内容搬进 `root`（新布局的根），并改写内容。`old` 与 `root` 可以相同（知识库）。"""
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
    # skill 上的证据 → usage 单元
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
        units.append({"id": uid, "content": f"{sid} 的效果记录（迁移自 v0.4 记在 skill 上的 {len(entries)} 条证据："
                                            f"支持 {len(supports)}，反驳 {len(decisive) - len(supports)}）。",
                      "form": "fact", "scope": "usage", "provenance": " ; ".join(sources), "status": status,
                      "condition": "由 v0.4 迁移；具体题型与样本见各条证据", "meta": {"of": sid, "migrated": True}})
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


def commit(path, message) -> None:
    if (path / ".git").exists():
        subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=Knosis", "-c", "user.email=knosis@localhost", "commit", "--quiet",
                        "--allow-empty", "-m", message], cwd=path, check=True, capture_output=True)


def migrate(path) -> dict:
    from string import Template

    path = Path(path).resolve()
    if (path / "kb").is_dir():
        return {"path": str(path), "skipped": "already v0.5"}
    if (path / ".knosis/state.json").exists() and (path / "knowledge").is_dir():
        report = {"path": str(path), "kind": "workspace", "current": convert(path / "knowledge", path), "snapshots": 0}
        for old in sorted(path.glob("stages/**/knowledge")):
            if (old / "units.jsonl").exists():
                convert(old, old.parent)
                report["snapshots"] += 1
        for used in path.glob("stages/**/*used_units.jsonl"):
            used.write_text(rewrite_text(used.read_text(encoding="utf-8")), encoding="utf-8")
        from ..workspace import TEMPLATES

        (path / "AGENTS.md").write_text(Template((TEMPLATES / "AGENTS.md").read_text(encoding="utf-8")).substitute(
            python=sys.executable), encoding="utf-8")
        commit(path, "migrate to v0.5 layout (kb/ + evidence/)")
        return report
    if (path / "units.jsonl").exists():
        report = {"path": str(path), "kind": "kb", "current": convert(path, path)}
        gitignore = path / ".gitignore"
        if gitignore.exists():
            gitignore.write_text(gitignore.read_text(encoding="utf-8").replace("outline.draft.yaml", "kb/outline.draft.yaml"),
                                 encoding="utf-8")
        commit(path, "migrate to v0.5 layout (kb/ + evidence/)")
        return report
    raise ValueError(f"{path}: not a v0.4 workspace or knowledge base")
