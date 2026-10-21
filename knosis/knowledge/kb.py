"""独立知识库（KB）：跨工作区持续积累的知识层，本身是一个 git 仓库，每次写回一个提交。

    kb/
    ├── units.jsonl  evidence.jsonl  ontology/  checks/  feedback/   与工作区 knowledge/ 同布局
    └── IMPORT.md    导入记录（如本体剔除 GT 的统计）

工作区 `ws init --kb` 从中继承（`inherit`），结束后 `merge` 写回；写回前跑 `check_knowledge`，不通过就拒绝。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .evidence import data_inputs, load_evidence, run_check
from .units import load_units, scope_of, write_units

PARTS = ("ontology", "checks", "skills", "feedback", "traces")
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
    write_units(kb / "units.jsonl", [])
    write_units(kb / "evidence.jsonl", [])
    git(kb, "init", "--quiet")
    commit(kb, "init")
    return kb


def inherit(kb, target, scopes=None) -> dict:
    """把 KB 当前版本复制到知识层目录 `target`；`scopes` 给定时只继承这些粒度的 κ（如只继承 method 元知识），
    本体属于 relation / dataset，只在继承这两者之一时一并复制。"""
    kb, target = Path(kb).resolve(), Path(target)
    units = load_units(kb / "units.jsonl")
    scopes = list(scopes) if scopes else None
    if scopes:
        kept = {u["id"] for u in units if scope_of(u) in scopes}
        # 只继承一部分时，被丢掉的父单元不再可解析，派生关系记进 meta。
        units = [{**u, "derived_from": [p for p in u.get("derived_from", []) if p in kept],
                  "meta": {**u.get("meta", {}), "inherited_derived_from": u.get("derived_from", [])}}
                 for u in units if u["id"] in kept]
    version = git(kb, "rev-parse", "--short", "HEAD")
    # 标记来自知识库：其中 `data/` 来源指向产生它时的环境，见 `source_issues`。
    units = [{**u, "meta": {**u.get("meta", {}), "inherited": u.get("meta", {}).get("inherited", version)}} for u in units]
    ids = {u["id"] for u in units}
    write_units(target / "units.jsonl", units)
    write_units(target / "evidence.jsonl", [{**e, "inherited": e.get("inherited", version)} for e in load_evidence(kb)
                                           if e["unit"] in ids or not scopes])
    for part in PARTS:
        wanted = {"ontology": {"relation", "dataset"}, "skills": {"skill"}}.get(part)
        if (kb / part).is_dir() and (not scopes or not wanted or wanted & set(scopes)):
            shutil.copytree(kb / part, target / part, dirs_exist_ok=True, ignore=IGNORE)
    return {"path": str(kb), "version": version, "scopes": scopes, "units": len(units)}


def seen_items(kb, benchmark, scenario) -> set:
    """KB 里同一数据集的反馈记录出现过的题目 id：新工作区的测试题要排除它们（mode=answer 时反馈带了正确答案）。"""
    records = [json.loads(p.read_text(encoding="utf-8")) for p in (Path(kb) / "feedback").glob("*.json")]
    return {item["id"] for r in records if (r.get("benchmark"), r.get("scenario")) == (benchmark, scenario)
            for item in r["items"]}


def portable(ws, unit) -> tuple[bool, str]:
    """在只含 `data/` 与 `knowledge/` 的临时工作区里跑单元的检查，结果与原地运行一致，才说明它不依赖本工作区的其他文件。"""
    here = run_check(unit, ws)[0]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "data").symlink_to(Path(ws).resolve() / "data")
        shutil.copytree(Path(ws) / "knowledge", tmp / "knowledge", ignore=IGNORE)
        verdict, note = run_check(unit, tmp)
    return verdict == here and "Traceback" not in note, note


def merge(ws, kb) -> str:
    """把工作区当前知识层写回 KB，返回新版本号。

    κ 按 id 合并（工作区版本覆盖，旧版本留在 KB 的 git 历史里）；证据追加未见过的；
    工作区新产生的反馈记录改名为 `<工作区名>.<id>`，并改写指向它们的来源；
    被引用的轨迹（`data/traces/<id>.jsonl`）复制进 KB 的 `traces/`，来源改写为 `knowledge/traces/...`，继承后仍能定位。
    """
    from . import check_knowledge
    from ..workspace import status

    ws, kb = Path(ws).resolve(), Path(kb).resolve()
    source, state = ws / "knowledge", status(ws)
    renames = {p.stem: f"{ws.name}.{p.stem}" for p in (source / "feedback").glob("*.json") if "." not in p.stem}

    def rewrite(text):
        text = text.replace("data/traces/", "knowledge/traces/")
        return re.sub(r"feedback:([^#;\s]+)", lambda m: f"feedback:{renames.get(m.group(1), m.group(1))}", text)

    # 可执行的元知识要能离开原工作区运行；跑不通的记一条「无法判定」证据，写回 KB。
    extra = []
    for unit in load_units(source / "units.jsonl"):
        if scope_of(unit) == "method" and unit.get("check", {}).get("kind") == "python":
            ok, note = portable(ws, unit)
            if not ok:
                extra.append({"unit": unit["id"], "verdict": "undetermined", "method": "check",
                              "source": f"check:{unit['id']}(portable)", "inputs": data_inputs(ws),
                              "note": f"检查脚本离开原工作区（只保留 data/ 与 knowledge/）运行不通：{note[-200:]}"})
    if extra:
        from .evidence import add_evidence

        add_evidence(source, extra)
    units = {u["id"]: u for u in load_units(kb / "units.jsonl")}
    units |= {u["id"]: json.loads(rewrite(json.dumps(u, ensure_ascii=False))) for u in load_units(source / "units.jsonl")}
    # 工作区里删掉、但仍被派生引用的单元，用它在历史快照里的最后版本补进 KB，保证 I1 在 KB 里也成立。
    from ..workspace import snapshots

    history = {u["id"]: u for d in snapshots(ws) for u in load_units(d / "units.jsonl")}
    missing = {p for u in units.values() for p in u.get("derived_from", [])} - set(units)
    units |= {uid: history[uid] for uid in missing if uid in history}
    old = load_evidence(kb)
    key = lambda e: (e["unit"], e["verdict"], e["source"], e["created"])  # noqa: E731
    known = {key(e) for e in old}
    new = [json.loads(rewrite(json.dumps(e, ensure_ascii=False))) for e in load_evidence(source)]
    new = [{**e, "id": f"e-{len(old) + i + 1:04d}"} for i, e in enumerate(x for x in new if key(x) not in known)]
    for part in ("ontology", "checks", "skills"):
        if (source / part).is_dir():
            shutil.copytree(source / part, kb / part, dirs_exist_ok=True, ignore=IGNORE)
    text = "".join(p.read_text(encoding="utf-8") for p in (source / "units.jsonl", source / "evidence.jsonl") if p.exists())
    cited = set(re.findall(r"data/traces/([^#;\s\"]+?)\.jsonl", text))
    for name in cited:
        for path in (ws / "data/traces").glob(f"{name}.*"):
            (kb / "traces").mkdir(exist_ok=True)
            shutil.copy2(path, kb / "traces" / path.name)
    (kb / "feedback").mkdir(exist_ok=True)
    for path in (source / "feedback").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["id"] = renames.get(path.stem, path.stem)
        record.setdefault("workspace", ws.name)
        record.setdefault("benchmark", state["benchmark"])
        record.setdefault("scenario", state["scenario"])
        (kb / "feedback" / f"{record['id']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for path in (kb / "skills").glob("*/SKILL.md"):
        text = path.read_text(encoding="utf-8")
        for old, new in renames.items():
            text = re.sub(rf"(?<![\w.]){re.escape(old)}(?![\w])", new, text)
        path.write_text(text, encoding="utf-8")
    write_units(kb / "units.jsonl", list(units.values()))
    write_units(kb / "evidence.jsonl", old + new)
    issues = check_knowledge(kb)
    if issues:
        git(kb, "checkout", "--", ".")
        git(kb, "clean", "-fdq")
        raise ValueError("merge rejected:\n" + "\n".join(issues))
    return commit(kb, f"merge {ws.name}: {state['benchmark']}/{state['scenario']}, {len(units)} units, +{len(new)} evidence")


def import_ontology(source, kb, strip=False) -> dict:
    """把一个已标注的本体单元（如 ontology-bench 的 annotations）导入 KB 的 `ontology/<单元名>/`。

    `strip`：剔除来自 benchmark GT 的部分（Power BI 关系、逐题变换等），见 `ontology.strip_gt`。
    """
    from .ontology import import_annotation

    kb = Path(kb).resolve()
    report = import_annotation(source, kb / "ontology", strip=strip)
    with (kb / "IMPORT.md").open("a", encoding="utf-8") as fh:
        fh.write(f"- {Path(source).name}（strip_gt={strip}）：{json.dumps(report, ensure_ascii=False)}\n")
    commit(kb, f"import ontology {Path(source).name} (strip={strip})")
    return report
