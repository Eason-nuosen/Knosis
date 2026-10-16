"""工作区：把四层串起来的编排。explore → extract → refine（多轮）→ decide，每次验收提交一次 git。

    ws/<name>/
    ├── BRIEF.md  AGENTS.md  CLAUDE.md  TOOLS.md
    ├── data/                 agent 可见的数据（只读）
    ├── tasks/dev.jsonl       开发题（无答案），可提交拿反馈
    ├── tasks/tasks.jsonl     decide 阶段才生成的测试题（无答案）
    ├── stages/{1_explore, 2_extract, 3_refine/round_<n>, 4_decide}/   每个版本的知识快照在 <阶段目录>/knowledge/
    ├── knowledge/            当前知识层：units.jsonl、ontology/、feedback/
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
from ..knowledge import check_ontology, check_units, feedback, load_ontology, load_units, refs, write_units
from .exporters import EXPORTERS

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


def init(benchmark, scenario, out=None, feedback="answer", budget=20, **options) -> Path:
    """`feedback` / `budget`：dev 题反馈的模式（answer / score / none）与提交次数上限；其余参数给导出器。"""
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
    write_units(ws / "tasks/dev.jsonl", exported["dev"])
    if options.get("root") is not None:
        options["root"] = str(Path(options["root"]).resolve())
    save_state(ws, {
        "benchmark": benchmark, "scenario": scenario, "options": options,
        "stage": "explore", "round": 1, "holdout": exported["holdout"],
        "output": exported["output"], "python": sys.executable,
        "feedback": {"mode": feedback if exported["dev"] else "none", "budget": budget},
        "created": datetime.now(timezone.utc).isoformat(),
    })
    subprocess.run(["git", "init", "--quiet"], cwd=ws, check=True, capture_output=True)
    commit(ws, "init")
    return ws


def feedback_note(ws, state) -> str:
    """阶段提示里关于 dev 反馈的一段话。"""
    if state["feedback"]["mode"] == "none":
        return "本工作区没有 dev 反馈。"
    note = (f"`tasks/dev.jsonl` 是开发题（与测试题不重叠）。按 decide 的交付格式回答（可以只答一部分），"
            f"运行 `knosis feedback submit <文件>` 得到逐题结果"
            f"{'和正确答案' if state['feedback']['mode'] == 'answer' else '（只给对错与分数）'}，"
            f"记录写入 `knowledge/feedback/`；本工作区还剩 {feedback.left(ws, state)} 次。")
    last = feedback.records(ws)[-1:]
    if last:
        note += f"\n最近一次反馈：`knowledge/feedback/{last[0]['id']}.json`，指标 {json.dumps(last[0]['metrics'], ensure_ascii=False)[:300]}。"
    return note


def next_prompt(ws) -> str:
    ws = Path(ws).resolve()
    state = status(ws)
    stage_dir(ws, state).mkdir(parents=True, exist_ok=True)
    if state["stage"] == "decide" and state["output"] and not (ws / "tasks/tasks.jsonl").exists():
        opts = state["options"]
        ds = load_dataset(state["benchmark"], state["scenario"], root=opts.get("root"))
        exported = EXPORTERS[state["benchmark"]](ds, ws, write_data=False, **opts)
        write_units(ws / "tasks/tasks.jsonl", exported["tasks"])
    template = (TEMPLATES / "stages" / f"{state['stage']}.md").read_text(encoding="utf-8")
    return Template(template).substitute(state, output=state["output"] or "（本数据集没有下游预测）",
                                         feedback=feedback_note(ws, state))


def prediction_ids(path) -> tuple[list, list]:
    """交付文件里的 id 与缺答案的 id。JSONL 每行 {id, answer}；CSV 有 row_id、prediction 两列。"""
    path = Path(path)
    if path.suffix == ".jsonl":
        rows = load_units(path)
        return [r["id"] for r in rows], [r["id"] for r in rows if "answer" not in r]
    import pandas as pd

    frame = pd.read_csv(path)
    if not {"row_id", "prediction"} <= set(frame.columns):
        raise ValueError(f"{path.name} requires row_id and prediction columns")
    return frame["row_id"].tolist(), frame.loc[frame["prediction"].isna(), "row_id"].tolist()


def prediction_issues(ws, state):
    if not state["output"]:
        return []
    path = stage_dir(ws, state) / state["output"]
    if not path.is_file() or not path.stat().st_size:
        return [f"missing or empty predictions: {path.relative_to(ws)}"]
    if not (ws / "tasks/tasks.jsonl").exists():
        return ["tasks/tasks.jsonl is missing; run knosis ws next first"]
    expected = {task["id"] for task in load_units(ws / "tasks/tasks.jsonl")}
    ids, missing_answers = prediction_ids(path)
    issues = []
    if set(ids) - expected:
        issues.append(f"unknown prediction ids: {sorted(set(ids) - expected, key=str)[:20]}")
    if expected - set(ids):
        issues.append(f"missing prediction ids: {sorted(expected - set(ids), key=str)[:20]}")
    if len(ids) != len(set(ids)):
        issues.append("duplicate prediction ids")
    if missing_answers:
        issues.append(f"missing answers: {missing_answers[:20]}")
    return issues


def snapshots(ws) -> list[Path]:
    """已保存的知识版本目录（`<阶段目录>/knowledge/`），按 K_0, K_1, … 排序。"""
    rounds = sorted((ws / "stages/3_refine").glob("round_*/knowledge"), key=lambda p: int(p.parent.name.split("_")[1]))
    return [p for p in [ws / "stages/2_extract/knowledge", *rounds] if p.exists()]


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
    """复制一整份知识层（units.jsonl、ontology/、feedback/）。"""
    shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))


def check(ws) -> list[str]:
    ws = Path(ws).resolve()
    state = status(ws)
    issues = stage_issues(ws, state)
    if issues:
        return issues
    stage = state["stage"]
    if stage in {"extract", "refine"}:
        copy_knowledge(ws / "knowledge", stage_dir(ws, state) / "knowledge")
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
        chosen = {"none": None, "K_final": ws / "knowledge", "K_0": ws / "stages/2_extract/knowledge"}[knowledge]
    else:
        chosen = ws / f"stages/3_refine/round_{int(knowledge.removeprefix('K_'))}/knowledge"
    # 对照副本不带未来的分析、预测或 git 历史；历史快照只保留所选版本及其之前的。
    shutil.copytree(ws, out, ignore=shutil.ignore_patterns(".git", "stages", "tasks", "knowledge", "runs.jsonl", "eval.json", "__pycache__"))
    for directory in STAGES.values():
        (out / "stages" / directory).mkdir(parents=True)
    (out / "tasks").mkdir()
    write_units(out / "tasks/dev.jsonl", load_units(ws / "tasks/dev.jsonl"))
    if chosen is None:
        write_units(out / "knowledge/units.jsonl", [])
    else:
        copy_knowledge(chosen, out / "knowledge")
        keep = versions if knowledge == "K_final" else versions[:versions.index(chosen) + 1]
        for directory in keep:
            copy_knowledge(directory, out / directory.relative_to(ws))
    state = status(out)
    # 对照组只比较给定的知识，decide 时不再拿新的反馈。
    state.update(stage="decide", knowledge=knowledge, feedback={**state["feedback"], "mode": "none"})
    state.pop("completed", None)
    save_state(out, state)
    subprocess.run(["git", "init", "--quiet"], cwd=out, check=True, capture_output=True)
    commit(out, f"fork: knowledge={knowledge}")
    return out


from .driver import agent_command, run  # noqa: E402,F401
