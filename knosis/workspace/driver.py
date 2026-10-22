"""驱动模式：由 Knosis 启动外部编码 agent（`codex exec` / `claude -p`）逐阶段完成并验收。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from ..knowledge import feedback, load_units
from . import check, goto, next_prompt, prediction_ids, save_state, stage_dir, stage_issues, status


def agent_command(agent, ws, prompt, model=None, effort=None):
    if agent == "codex":
        return ["codex", "exec", "-C", str(ws), "--sandbox", "workspace-write", "--skip-git-repo-check",
                *(["-m", model] if model else []), *(["-c", f'model_reasoning_effort="{effort}"'] if effort else []), prompt]
    if agent == "claude":
        return ["claude", "-p", prompt, "--permission-mode", "acceptEdits", *(["--model", model] if model else []),
                "--allowedTools", "Bash", "Read", "Edit", "Write"]
    raise ValueError(f"unknown agent: {agent}")


def submit_round(ws, state, directory) -> None:
    """自动 RSI：refine 每轮结束时，把本轮的 dev 预测提交一次反馈，结果进入下一轮的提示。"""
    path = directory / f"dev_{state['output']}"
    submitted = {r["submitted"] for r in feedback.own(ws)}
    if path.exists() and str(path.relative_to(ws)) not in submitted and feedback.left(ws, state) > 0:
        dev = {t["id"] for t in load_units(ws / "tasks/dev.jsonl")}
        ids, _ = prediction_ids(path)
        # 要求全做时不完整的文件不提交，由验收报出缺题，带着问题重试。
        if not state["feedback"].get("full") or dev <= set(ids):
            feedback.submit(ws, path)


def knowledge_dir(path) -> tuple[Path, Path | None]:
    """（知识层目录, 工作区根）：工作区的知识层在 knowledge/；知识库本身就是知识层目录，没有工作区根。"""
    path = Path(path).resolve()
    return (path / "knowledge", path) if (path / "knowledge").is_dir() else (path, None)


def organize_prompt(path) -> str:
    from string import Template

    from ..knowledge import INACTIVE, check_knowledge, outline
    from . import TEMPLATES

    kdir, root = knowledge_dir(path)
    draft = outline.write_outline(kdir, outline.draft(kdir), "outline.draft.yaml")
    items = outline.members(kdir)
    before = [i for i in check_knowledge(kdir, root=root) if not i.startswith("outline")]
    note = ("（以下是整理前就有的问题，与本任务无关，可以保留：" + "；".join(before[:10]) + "）") if before else ""
    return Template((TEMPLATES / "organize.md").read_text(encoding="utf-8")).substitute(
        kdir=kdir, ws=path, draft=draft, check_note=note,
        existing=("已有大纲 `outline.yaml`：在它的基础上更新，保留合理的结构，把「未归类」的新知识放进去，"
                  "必要时拆分或合并节（`knosis knowledge outline --ws " + str(path) + "` 看当前大纲与未归类单元）。"
                  if outline.load_outline(kdir) is not None else "还没有大纲，从草稿出发。"),
        n_units=sum(1 for i in items.values() if i.get("form") != "skill" and not i["id"].startswith("ontology/")),
        n_skills=sum(1 for i in items.values() if i.get("form") == "skill"),
        n_inactive=sum(1 for i in items.values() if i.get("status") in INACTIVE))


def organize_issues(path) -> list[str]:
    from ..knowledge import check_knowledge, outline

    kdir, root = knowledge_dir(path)
    current = outline.load_outline(kdir)
    if current is None:
        return [f"missing {kdir / outline.FILE}"]
    items = outline.members(kdir)
    left = outline.unplaced(current, items)
    issues = [i for i in check_knowledge(kdir, root=root) if i.startswith("outline")]
    return issues + ([f"outline: {len(left)} active units not placed: {', '.join(left[:20])}"] if left else [])


def organize(path, agent="codex", model=None, effort=None) -> list[str]:
    """让 agent 结合已有知识整理出知识体系（outline.yaml）；不通过时带着问题重试一次，返回最后的问题清单。"""
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("nested agent runs are disabled (KNOSIS_DEPTH >= 1)")
    kdir, root = knowledge_dir(path)
    cwd = root or kdir
    prompt, issues = organize_prompt(path), []
    env = {**os.environ, "KNOSIS_DEPTH": "1"}
    for attempt in range(2):
        started = time.monotonic()
        with (kdir / "organize.log").open("a", encoding="utf-8") as log:
            result = subprocess.run(agent_command(agent, cwd, prompt, model, effort), cwd=cwd, env=env,
                                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"{agent} exited with {result.returncode}; see {kdir / 'organize.log'}")
        issues = organize_issues(path)
        print(json.dumps({"attempt": attempt + 1, "seconds": round(time.monotonic() - started), "issues": issues},
                         ensure_ascii=False))
        if not issues:
            break
        prompt += "\n验收未通过，请修正：\n" + "\n".join(issues)
    return issues


def run(ws, agent="codex", stages=None, rounds=1, model=None, effort=None, note=None) -> None:
    """每阶段失败后带着验收问题重试一次；记录写入 `.knosis/runs.jsonl`。`note`：附加在每个阶段提示末尾的实验说明。"""
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("nested agent runs are disabled (KNOSIS_DEPTH >= 1)")
    ws = Path(ws).resolve()
    env = {**os.environ, "KNOSIS_DEPTH": "1"}
    for stage in stages or ["explore", "extract"]:
        goto(ws, stage)
        for _ in range(rounds if stage == "refine" else 1):
            prompt = next_prompt(ws) + (f"\n\n## 本次实验的附加要求\n\n{note}\n" if note else "") + \
                "\n驱动模式：由运行器验收和提交，不要自行运行 ws check 或切换阶段。"
            directory = stage_dir(ws, status(ws))
            issues = []
            for attempt in range(2):
                started = time.monotonic()
                before = status(ws)
                with (directory / "agent.log").open("a", encoding="utf-8") as log:
                    # stdin 必须关掉：codex exec 在 stdin 未关闭时会一直等待追加输入。
                    result = subprocess.run(agent_command(agent, ws, prompt, model, effort), cwd=ws, env=env,
                                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
                if result.returncode:
                    raise RuntimeError(f"{agent} exited with {result.returncode}; see {directory / 'agent.log'}")
                if stage == "refine":
                    submit_round(ws, before, directory)
                # agent 偶尔自行验收；仍检查原阶段交付，不能用切换状态绕过验收。
                if status(ws) == before:
                    issues = check(ws)
                else:
                    issues = stage_issues(ws, before)
                    if issues:
                        save_state(ws, before)
                record = {"stage": stage, "round": before["round"], "attempt": attempt + 1,
                          "agent": agent, "model": model, "effort": effort, "note": note, "seconds": time.monotonic() - started,
                          "units": len(load_units(ws / "knowledge/units.jsonl")), "issues": issues}
                with (ws / ".knosis/runs.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                if not issues:
                    break
                prompt += "\n验收未通过，请修正：\n" + "\n".join(issues)
            if issues:
                raise RuntimeError("\n".join(issues))
        if stage == "refine":
            goto(ws, "decide")
