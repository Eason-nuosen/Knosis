"""Workspace: orchestration tying the four layers together. explore -> extract -> refine (multiple rounds) -> decide, with a git commit after each acceptance check.

    ws/<name>/
    ├── BRIEF.md  AGENTS.md  CLAUDE.md  TOOLS.md
    ├── data/                 data visible to the agent (read-only)
    ├── tasks/dev.jsonl       dev tasks (no answers); submit for feedback
    ├── tasks/tasks.jsonl     test tasks generated only at decide (no answers)
    ├── stages/{0_inherit, 1_explore, 2_extract, 3_refine/round_<n>, 4_decide}/   each version's knowledge snapshot is in <stage dir>/{kb,evidence}/
    ├── kb/                   current knowledge: knowledge/{units.jsonl, ontology/}, skills/, outline.yaml
    ├── evidence/             provenance and verification: ledger.jsonl, checks/, feedback/, consolidate.jsonl
    └── .knosis/state.json
"""

from __future__ import annotations

import inspect
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from ..data import LOADERS, load_dataset
from ..knowledge import check_knowledge, check_units, ensure, feedback, layout, load_units, ontology_docs, scope_of, write_units
from ..knowledge.layout import CHECKS, PARTS
from ..knowledge.kb import inherit, seen_items
from ..lang import t
from .exporters import EXPORTERS

TEMPLATES = Path(__file__).parent / "templates"  # English; templates_cn/ holds the Chinese ones (KNOSIS_LANG=zh)


def templates() -> Path:
    from ..lang import localized

    return localized(TEMPLATES)
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


def open_dataset(benchmark, scenario, options):
    """Load the raw dataset from workspace options: pass only the args the loader knows (root, market, task ...); the rest go to the exporter."""
    accepted = inspect.signature(LOADERS[benchmark]).parameters
    return load_dataset(benchmark, scenario, **{k: v for k, v in options.items() if k in accepted})


def commit(ws, message):
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Knosis", "-c", "user.email=knosis@localhost",
         "commit", "--quiet", "--allow-empty", "-m", message],
        cwd=ws, check=True, capture_output=True,
    )


def init(benchmark, scenario, out=None, feedback="answer", budget=20, kb=None, kb_scope=None, feedback_full=False, **options) -> Path:
    """`feedback` / `budget`：dev feedback mode (answer / score / none) and submission limit;
    `kb`: inherit initial knowledge from a standalone knowledge base (`kb_scope` limits it to these granularities, e.g. ["method"]), snapshotted as K_inherit;
    `feedback_full`: every submission must cover all dev tasks (by default a subset is allowed); other args go to the exporter."""
    from ..tools import tools_markdown

    ws = Path(out or f"ws/{benchmark}-{scenario}").resolve()
    ws.mkdir(parents=True, exist_ok=False)
    exported = EXPORTERS[benchmark](open_dataset(benchmark, scenario, options), ws, **options)
    for directory in ("tasks", ".knosis", *(f"stages/{s}" for s in STAGES.values())):
        (ws / directory).mkdir(parents=True, exist_ok=True)
    ensure(ws)
    (ws / "BRIEF.md").write_text(exported["brief"], encoding="utf-8")
    agents = Template((templates() / "AGENTS.md").read_text(encoding="utf-8")).substitute(python=sys.executable)
    (ws / "AGENTS.md").write_text(agents, encoding="utf-8")
    (ws / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    (ws / "TOOLS.md").write_text(tools_markdown(exported["modalities"]), encoding="utf-8")
    (ws / ".gitignore").write_text("__pycache__/\n*.pyc\n.knosis/runs.jsonl\n.knosis/eval.json\nview/\n", encoding="utf-8")
    inherited, exclude = None, []
    if kb:
        inherited = inherit(kb, ws, kb_scope)
        copy_knowledge(ws, ws / "stages/0_inherit")
        # Inherited feedback may contain answers: on the same dataset, tasks it covers are excluded from the test set.
        seen = seen_items(kb, benchmark, scenario)
        exclude = [t["id"] for t in exported["tasks"] if t["id"] in seen]
    write_units(ws / "tasks/dev.jsonl", exported["dev"])
    if inherited:
        from ..knowledge import ontology_docs

        names = ", ".join(f"`{n or 'ontology'}`" for n in ontology_docs(ws)) or t("none", "无")
        with (ws / "BRIEF.md").open("a", encoding="utf-8") as fh:
            fh.write(t(f"\n## Inherited knowledge\n\nThis workspace inherited {inherited['units']} κ and the ontology {names} from a standalone knowledge base"
                       f" (already in `kb/`, evidence in `evidence/`, verbatim snapshot in `stages/0_inherit/`). They come from other tasks or other people's annotations"
                       " and are not necessarily correct or applicable to the task here: pick with `knosis knowledge select`, and adopt, revise, narrow or retract them based on evidence.\n",
                       f"\n## 继承的知识\n\n本工作区从独立知识库继承了 {inherited['units']} 条 κ 与本体 {names}"
                       f"（已在 `kb/`，证据在 `evidence/`，原样快照在 `stages/0_inherit/`）。它们来自别的任务或别人的标注，"
                       "未必正确、未必适用于这里的任务：用 `knosis knowledge select` 挑选，按证据采用、修正、收窄或撤回。\n"))
    if options.get("root") is not None:
        options["root"] = str(Path(options["root"]).resolve())
    save_state(ws, {
        "benchmark": benchmark, "scenario": scenario, "options": options,
        "stage": "explore", "round": 1, "holdout": exported["holdout"],
        "output": exported["output"], "extras": exported.get("extras", []), "python": sys.executable,
        "feedback": {"mode": feedback if exported["dev"] else "none", "budget": budget,
                     "full": bool(feedback_full)},
        **({"kb": inherited, "exclude": exclude} if kb else {}),
        "created": datetime.now(timezone.utc).isoformat(),
    })
    subprocess.run(["git", "init", "--quiet"], cwd=ws, check=True, capture_output=True)
    commit(ws, "init")
    return ws


def feedback_note(ws, state) -> str:
    """The paragraph about dev feedback in stage prompts."""
    if state["feedback"]["mode"] == "none":
        return t("This workspace has no dev feedback.", "本工作区没有 dev 反馈。")
    answer = state['feedback']['mode'] == 'answer'
    full = state['feedback'].get('full')
    left = feedback.left(ws, state)
    note = t(f"`tasks/dev.jsonl` holds dev tasks (disjoint from the test tasks). Answer them in the decide deliverable format and "
             f"run `knosis feedback submit <file>` to get per-task results"
             f"{' and the correct answers' if answer else ' (correctness and scores only)'}; "
             f"{'every submission must answer all dev tasks' if full else 'you may choose which dev tasks to answer'}. "
             f"Review each task's result: both correct and wrong answers can yield knowledge (write the basis as evidence, method=feedback); "
             f"records go to `evidence/feedback/`. This workspace has {left} submissions left.",
             f"`tasks/dev.jsonl` 是开发题（与测试题不重叠）。按 decide 的交付格式回答，"
             f"运行 `knosis feedback submit <文件>` 得到逐题结果"
             f"{'和正确答案' if answer else '（只给对错与分数）'}，"
             f"{'每次必须回答全部开发题' if full else '可以自己选择回答哪些开发题'}；"
             f"回看每道题的结果，答对和答错的都可以总结出知识（依据写成证据，method=feedback），"
             f"记录写入 `evidence/feedback/`；本工作区还剩 {left} 次。")
    last = feedback.own(ws)[-1:]
    if last:
        metrics = json.dumps(last[0]['metrics'], ensure_ascii=False)[:300]
        note += t(f"\nLatest feedback: `evidence/feedback/{last[0]['id']}.json`, metrics {metrics}.",
                  f"\n最近一次反馈：`evidence/feedback/{last[0]['id']}.json`，指标 {metrics}。")
    return note


def next_prompt(ws) -> str:
    ws = Path(ws).resolve()
    state = status(ws)
    stage_dir(ws, state).mkdir(parents=True, exist_ok=True)
    if state["stage"] == "decide" and state["output"] and not (ws / "tasks/tasks.jsonl").exists():
        opts = state["options"]
        ds = open_dataset(state["benchmark"], state["scenario"], opts)
        exported = EXPORTERS[state["benchmark"]](ds, ws, write_data=False, **opts)
        exclude = set(state.get("exclude", []))
        write_units(ws / "tasks/tasks.jsonl", [t for t in exported["tasks"] if t["id"] not in exclude])
    template = (templates() / "stages" / f"{state['stage']}.md").read_text(encoding="utf-8")
    note = control_note() if state.get("knowledge") == "none" else ""
    # Templates always include $control; older workspaces' templates may not, so missing variables are treated as empty.
    return Template(template).substitute({"control": "", "feedback": "", **state},
                                         output=state["output"] or t("(this dataset has no downstream prediction)", "（本数据集没有下游预测）"),
                                         feedback=feedback_note(ws, state), control=note)


def control_note() -> str:
    return t("\n\n## Control condition\n\nThis is a control workspace: the knowledge layer is this round's baseline. **Do not add knowledge units or methods**,"
             " and do not write reusable detection scripts in the workspace. Complete the tasks and deliverables directly using only the data, tools and common sense.\n",
             "\n\n## 对照条件\n\n这是对照工作区：知识层为本轮的 baseline，**不要新增知识单元或方法**，"
             "也不要在 workspace 里写可复用的检测脚本。只用数据、工具和常识直接完成任务与交付。\n")


def prediction_ids(path) -> tuple[list, list]:
    """Ids in the deliverable and ids missing an answer. JSONL: one {id, answer} per line; CSV: row_id and prediction columns."""
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
    extras = [f"missing or empty {name}: stages/4_decide/{name}" for name in state.get("extras", [])
              if not (ws / "stages/4_decide" / name).is_file() or not (ws / "stages/4_decide" / name).stat().st_size]
    if not state["output"]:
        return extras
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
    return issues + extras


def snapshots(ws) -> list[Path]:
    """Saved knowledge versions (stage dirs containing `kb/`, same layout as the workspace), ordered K_inherit, K_0, K_1, ..."""
    ws = Path(ws)
    rounds = sorted((ws / "stages/3_refine").glob("round_*"), key=lambda p: int(p.name.split("_")[1]))
    return [p for p in [ws / "stages/0_inherit", ws / "stages/2_extract", *rounds] if (p / "kb").is_dir()]


def stage_issues(ws, state):
    units = load_units(layout(ws).units)
    history = {}
    for directory in snapshots(ws):
        history.update((u["id"], u) for u in load_units(layout(directory).units))
    docs = ontology_docs(ws)
    # Keep the last state of past units so deleting a unit cannot bypass retraction propagation.
    effective = {**history, **{u["id"]: u for u in units if u.get("id")}}
    issues = check_knowledge(ws, known_ids=set(history), root=ws)
    issues += check_units(list(effective.values()), root=ws)
    directory = stage_dir(ws, state)
    required = {"explore": "notes.md", "refine": "changelog.md"}
    if state["stage"] in required:
        path = directory / required[state["stage"]]
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            issues.append(f"missing or empty {path.relative_to(ws)}")
    if state["stage"] == "extract" and not units and not docs:
        issues.append("extract requires nonempty kb/knowledge/units.jsonl or kb/knowledge/ontology/")
    if state["stage"] in {"extract", "refine"}:
        from ..knowledge.kb import portable

        # Method knowledge must be reproducible by others: its check script may depend only on data/, kb/ and evidence/.
        for unit in units:
            if scope_of(unit) == "method" and unit.get("check", {}).get("kind") == "python" and unit["status"] not in {"retracted", "stale", "merged"}:
                if not unit["check"]["path"].startswith(f"{CHECKS}/"):
                    issues.append(f"{unit['id']}: method check must live under {CHECKS}/")
                elif not portable(ws, unit)[0]:
                    issues.append(f"{unit['id']}: method check is not self-contained (fails with only data/, kb/ and evidence/)")
    if state["stage"] == "refine" and state["feedback"].get("full") and state["feedback"]["mode"] != "none":
        path = directory / f"dev_{state['output']}"
        dev = {t["id"] for t in load_units(ws / "tasks/dev.jsonl")}
        if not path.exists() or dev - set(prediction_ids(path)[0]):
            issues.append(f"{path.relative_to(ws)} must answer all {len(dev)} dev tasks")
    if state["stage"] == "decide":
        issues.extend(prediction_issues(ws, state))
    return list(dict.fromkeys(issues))


def copy_knowledge(source, target):
    """Copy the whole knowledge layer (`kb/` and `evidence/`) to another root (snapshot or control copy)."""
    for part in PARTS:
        if (Path(source) / part).is_dir():
            shutil.copytree(Path(source) / part, Path(target) / part, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.log", "outline.draft.yaml"))


def check(ws) -> list[str]:
    ws = Path(ws).resolve()
    state = status(ws)
    issues = stage_issues(ws, state)
    if issues:
        return issues
    stage = state["stage"]
    if stage in {"extract", "refine"}:
        copy_knowledge(ws, stage_dir(ws, state))
    message = f"{stage}" + (f" round {state['round']}" if stage == "refine" else "")
    if stage == "refine":
        state["round"] += 1
    elif stage == "decide":
        state["completed"] = True
    else:
        state["stage"] = {"explore": "extract", "extract": "refine"}[stage]
    save_state(ws, state)
    commit(ws, f"{message}: {len(load_units(layout(ws).units))} units")
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


def fork(ws, out, knowledge="K_final", drop=()) -> Path:
    """Copy for a decide control: knowledge is none / K_inherit / K_0 / K_<n> / K_final;
    `drop`: additionally remove these units (single-unit ablation, to test whether it helps the task)."""
    ws, out = Path(ws).resolve(), Path(out).resolve()
    if out == ws or out.is_relative_to(ws):
        raise ValueError("fork output must be outside the source workspace")
    versions = snapshots(ws)
    if knowledge in {"none", "K_final", "K_0", "K_inherit"}:
        chosen = {"none": None, "K_final": ws, "K_0": ws / "stages/2_extract",
                  "K_inherit": ws / "stages/0_inherit"}[knowledge]
    else:
        chosen = ws / f"stages/3_refine/round_{int(knowledge.removeprefix('K_'))}"
    # The control copy carries no later analysis, predictions or git history; only snapshots up to the chosen version are kept.
    shutil.copytree(ws, out, ignore=shutil.ignore_patterns(".git", "stages", "tasks", *PARTS, "runs.jsonl", "eval.json", "__pycache__"))
    for directory in STAGES.values():
        (out / "stages" / directory).mkdir(parents=True)
    (out / "tasks").mkdir()
    write_units(out / "tasks/dev.jsonl", load_units(ws / "tasks/dev.jsonl"))
    ensure(out)
    if chosen is not None:
        copy_knowledge(chosen, out)
        keep = versions if knowledge == "K_final" else versions[:versions.index(chosen) + 1]
        for directory in keep:
            copy_knowledge(directory, out / directory.relative_to(ws))
        units = load_units(layout(out).units)
        write_units(layout(out).units, [u for u in units if u["id"] not in set(drop)])
    state = status(out)
    # Controls compare only the given knowledge; no new feedback during decide.
    state.update(stage="decide", knowledge=knowledge, dropped=list(drop), feedback={**state["feedback"], "mode": "none"})
    state.pop("completed", None)
    save_state(out, state)
    subprocess.run(["git", "init", "--quiet"], cwd=out, check=True, capture_output=True)
    commit(out, f"fork: knowledge={knowledge}")
    return out


from .driver import agent_command, run  # noqa: E402,F401
