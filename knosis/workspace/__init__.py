"""工作区：把四层串起来的编排。explore → extract → refine（多轮）→ decide，每次验收提交一次 git。

    ws/<name>/
    ├── BRIEF.md  AGENTS.md  CLAUDE.md  TOOLS.md
    ├── data/                 agent 可见的数据（只读）
    ├── tasks/tasks.jsonl     decide 阶段才生成的无答案题目
    ├── stages/{1_explore, 2_extract, 3_refine/round_<n>, 4_decide}/
    ├── knowledge/units.jsonl  knowledge/ontology/   当前知识层
    └── .knosis/state.json
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from ..data import load_dataset
from ..knowledge import check_ontology, check_units, load_ontology, load_units, refs, write_units
from .export import EXPORTERS

TEMPLATES = Path(__file__).parent / "templates"
STAGES = {"explore": "1_explore", "extract": "2_extract", "refine": "3_refine", "decide": "4_decide"}


def status(ws) -> dict:
    return json.loads((Path(ws) / ".knosis/state.json").read_text(encoding="utf-8"))


def save_state(ws, state):
    (Path(ws) / ".knosis/state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )


def stage_dir(ws, state):
    path = Path(ws) / "stages" / STAGES[state["stage"]]
    return path / f"round_{state['round']}" if state["stage"] == "refine" else path


def commit(ws, message):
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Knosis", "-c", "user.email=knosis@localhost",
         "commit", "--quiet", "--allow-empty", "-m", message],
        cwd=ws, check=True, capture_output=True,
    )


def init(benchmark, scenario, out=None, **options) -> Path:
    from ..tools import tools_markdown

    ws = Path(out or f"ws/{benchmark}-{scenario}").resolve()
    ws.mkdir(parents=True, exist_ok=False)
    exported = EXPORTERS[benchmark](load_dataset(benchmark, scenario, root=options.get("root")), ws, **options)
    for directory in ("tasks", "knowledge", ".knosis", *(f"stages/{s}" for s in STAGES.values())):
        (ws / directory).mkdir(parents=True, exist_ok=True)
    (ws / "BRIEF.md").write_text(exported["brief"], encoding="utf-8")
    agents = Template((TEMPLATES / "AGENTS.md").read_text(encoding="utf-8")).substitute(python=sys.executable)
    (ws / "AGENTS.md").write_text(agents, encoding="utf-8")
    (ws / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    (ws / "TOOLS.md").write_text(tools_markdown(exported["modalities"]), encoding="utf-8")
    (ws / ".gitignore").write_text("__pycache__/\n*.pyc\n.knosis/runs.jsonl\n.knosis/eval.json\n", encoding="utf-8")
    write_units(ws / "knowledge/units.jsonl", [])
    if options.get("root") is not None:
        options["root"] = str(Path(options["root"]).resolve())
    save_state(ws, {
        "benchmark": benchmark, "scenario": scenario, "options": options,
        "stage": "explore", "round": 1, "holdout": exported["holdout"],
        "output": exported["output"], "python": sys.executable,
        "created": datetime.now(timezone.utc).isoformat(),
    })
    subprocess.run(["git", "init", "--quiet"], cwd=ws, check=True, capture_output=True)
    commit(ws, "init")
    return ws


def next_prompt(ws) -> str:
    ws = Path(ws).resolve()
    state = status(ws)
    stage_dir(ws, state).mkdir(parents=True, exist_ok=True)
    if state["stage"] == "decide" and not (ws / "tasks/tasks.jsonl").exists():
        opts = state["options"]
        ds = load_dataset(state["benchmark"], state["scenario"], root=opts.get("root"))
        exported = EXPORTERS[state["benchmark"]](ds, ws, write_data=False, **opts)
        write_units(ws / "tasks/tasks.jsonl", exported["tasks"])
    template = (TEMPLATES / "stages" / f"{state['stage']}.md").read_text(encoding="utf-8")
    return Template(template).substitute(state)


def prediction_issues(ws, state):
    path = stage_dir(ws, state) / state["output"]
    if not path.is_file() or not path.stat().st_size:
        return [f"missing or empty predictions: {path.relative_to(ws)}"]
    tasks_path = ws / "tasks/tasks.jsonl"
    if not tasks_path.exists():
        return ["tasks/tasks.jsonl is missing; run knosis ws next first"]
    if state["output"] == "predictions.jsonl":
        expected = {task["id"] for task in load_units(tasks_path)}
        predictions = load_units(path)
        ids = [prediction["id"] for prediction in predictions]
        missing_answers = [p["id"] for p in predictions if "answer" not in p]
    else:
        import pandas as pd

        predictions = pd.read_csv(path)
        if not {"row_id", "prediction"} <= set(predictions.columns):
            return ["predictions.csv requires row_id and prediction columns"]
        expected = set(pd.read_parquet(ws / "data/test_features.parquet")["row_id"])
        ids = predictions["row_id"].tolist()
        missing_answers = predictions.loc[predictions["prediction"].isna(), "row_id"].tolist()
    issues = []
    if set(ids) - expected:
        issues.append(f"unknown prediction ids: {sorted(set(ids) - expected)[:20]}")
    if expected - set(ids):
        issues.append(f"missing prediction ids: {sorted(expected - set(ids))[:20]}")
    if len(ids) != len(set(ids)):
        issues.append("duplicate prediction ids")
    if missing_answers:
        issues.append(f"missing answers: {missing_answers[:20]}")
    return issues


def snapshots(ws) -> list[Path]:
    """已保存的知识版本目录，按 K_0, K_1, … 排序。"""
    rounds = sorted((ws / "stages/3_refine").glob("round_*/units.jsonl"), key=lambda p: int(p.parent.name.split("_")[1]))
    return [p.parent for p in [ws / "stages/2_extract/units.jsonl", *rounds] if p.exists()]


def stage_issues(ws, state):
    units = load_units(ws / "knowledge/units.jsonl")
    history = {}
    for directory in snapshots(ws):
        history.update((u["id"], u) for u in load_units(directory / "units.jsonl"))
    docs = load_ontology(ws / "knowledge/ontology") if (ws / "knowledge/ontology").is_dir() else {}
    # 保留历史单元的最后状态，使删除单元不能绕过撤回传播。
    effective = {**history, **{u["id"]: u for u in units if u.get("id")}}
    issues = check_ontology(docs)
    issues += check_units(units, known_ids=history, root=ws, ontology_refs=refs(docs) if docs else None)
    issues += check_units(list(effective.values()), root=ws)
    directory = stage_dir(ws, state)
    required = {"explore": "notes.md", "refine": "changelog.md"}
    if state["stage"] in required:
        path = directory / required[state["stage"]]
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            issues.append(f"missing or empty {path.relative_to(ws)}")
    if state["stage"] == "extract" and not units and not docs:
        issues.append("extract requires nonempty knowledge/units.jsonl or knowledge/ontology/")
    if state["stage"] == "decide":
        issues.extend(prediction_issues(ws, state))
    return list(dict.fromkeys(issues))


def copy_knowledge(source, target):
    """复制一个知识版本：`units.jsonl` 与可选的 `ontology/`。"""
    write_units(target / "units.jsonl", load_units(source / "units.jsonl"))
    if (source / "ontology").is_dir():
        shutil.copytree(source / "ontology", target / "ontology", dirs_exist_ok=True)


def check(ws) -> list[str]:
    ws = Path(ws).resolve()
    state = status(ws)
    issues = stage_issues(ws, state)
    if issues:
        return issues
    stage = state["stage"]
    if stage in {"extract", "refine"}:
        copy_knowledge(ws / "knowledge", stage_dir(ws, state))
    message = f"{stage}" + (f" round {state['round']}" if stage == "refine" else "")
    if stage == "refine":
        state["round"] += 1
    elif stage == "decide":
        state["completed"] = True
    else:
        state["stage"] = {"explore": "extract", "extract": "refine"}[stage]
    save_state(ws, state)
    commit(ws, f"{message}: {len(load_units(ws / 'knowledge/units.jsonl'))} units")
    return []


def goto(ws, stage) -> None:
    STAGES[stage]
    state = status(ws)
    if state["stage"] == stage and not state.get("completed"):
        return
    state["stage"] = stage
    state.pop("completed", None)
    save_state(ws, state)
    commit(ws, f"goto: {stage}")


def fork(ws, out, knowledge="K_final") -> Path:
    """decide 对照用的副本：knowledge 为 none / K_0 / K_<n> / K_final。"""
    ws, out = Path(ws).resolve(), Path(out).resolve()
    if out == ws or out.is_relative_to(ws):
        raise ValueError("fork output must be outside the source workspace")
    versions = snapshots(ws)
    if knowledge in {"none", "K_final", "K_0"}:
        chosen = {"none": None, "K_final": ws / "knowledge", "K_0": ws / "stages/2_extract"}[knowledge]
    else:
        chosen = ws / f"stages/3_refine/round_{int(knowledge.removeprefix('K_'))}"
    # 对照副本不带未来的分析、预测或 git 历史；历史快照只保留所选版本及其之前的。
    shutil.copytree(ws, out, ignore=shutil.ignore_patterns(".git", "stages", "tasks", "knowledge", "runs.jsonl", "eval.json", "__pycache__"))
    for directory in STAGES.values():
        (out / "stages" / directory).mkdir(parents=True)
    (out / "tasks").mkdir()
    if chosen is None:
        write_units(out / "knowledge/units.jsonl", [])
    else:
        copy_knowledge(chosen, out / "knowledge")
        keep = versions if knowledge == "K_final" else versions[:versions.index(chosen) + 1]
        for directory in keep:
            copy_knowledge(directory, out / directory.relative_to(ws))
    state = status(out)
    state.update(stage="decide", knowledge=knowledge)
    state.pop("completed", None)
    save_state(out, state)
    subprocess.run(["git", "init", "--quiet"], cwd=out, check=True, capture_output=True)
    commit(out, f"fork: knowledge={knowledge}")
    return out


from .driver import agent_command, run  # noqa: E402,F401
