"""驱动模式：由 Knosis 启动外部编码 agent（`codex exec` / `claude -p`）逐阶段完成并验收。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from ..knowledge import feedback, layout, load_units
from . import check, goto, next_prompt, prediction_ids, save_state, stage_dir, stage_issues, status


def agent_command(agent, ws, prompt, model=None, effort=None):
    if agent == "codex":
        return ["codex", "exec", "-C", str(ws), "--sandbox", "workspace-write", "--skip-git-repo-check",
                *(["-m", model] if model else []), *(["-c", f'model_reasoning_effort="{effort}"'] if effort else []), prompt]
    if agent == "claude":
        return ["claude", "-p", prompt, "--permission-mode", "acceptEdits", *(["--model", model] if model else []),
                *(["--effort", effort] if effort else []),
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


def organize(path, agent="codex", model=None, effort=None) -> list[str]:
    """只做内化的「构建知识体系」一步（见 `knowledge.consolidate`），返回最后的问题清单。"""
    from ..knowledge import consolidate

    return consolidate.run(path, ["organize"], agent, model, effort)[0]["issues"]


def run(ws, agent="codex", stages=None, rounds=1, model=None, effort=None, note=None, consolidate=False) -> None:
    """每阶段失败后带着验收问题重试一次；记录写入 `.knosis/runs.jsonl`。`note`：附加在每个阶段提示末尾的实验说明。
    `consolidate`：refine 全部轮次结束、进入 decide 之前做一次内化（去重 → 矛盾处理 → 构建知识体系），
    通过后把知识层再快照为最后一轮之后的版本。"""
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
                          "units": len(load_units(layout(ws).units)), "issues": issues}
                with (ws / ".knosis/runs.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                if not issues:
                    break
                prompt += "\n验收未通过，请修正：\n" + "\n".join(issues)
            if issues:
                raise RuntimeError("\n".join(issues))
        if stage == "refine":
            if consolidate:
                consolidate_ws(ws, agent, model, effort)
            goto(ws, "decide")


def consolidate_ws(ws, agent, model, effort) -> None:
    """refine 之后的内化；结果与耗时记进 runs.jsonl，通过的步骤会改变知识层，再提交一次 refine 版本作为 K_final。"""
    from ..knowledge import consolidate

    results = consolidate.run(ws, agent=agent, model=model, effort=effort)
    with (ws / ".knosis/runs.jsonl").open("a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps({"stage": "consolidate", **r, "agent": agent, "model": model, "effort": effort,
                                 "units": len(load_units(layout(ws).units))}, ensure_ascii=False) + "\n")
    if any(not r["issues"] for r in results):
        # 内化发生在最后一轮 refine 之后：快照为下一个 refine 版本（K_final），每步已各自验收过。
        from . import commit, copy_knowledge

        state = status(ws)
        state["stage"] = "refine"
        directory = stage_dir(ws, state)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "changelog.md").write_text("# 内化\n\n" + "\n".join(
            f"- {r['step']}：{'通过' if not r['issues'] else '未通过，已恢复'}，操作 {json.dumps(r.get('actions', {}), ensure_ascii=False)}"
            for r in results) + "\n", encoding="utf-8")
        copy_knowledge(ws, directory)
        state["round"] += 1
        save_state(ws, state)
        commit(ws, f"consolidate: {len(load_units(layout(ws).units))} units")
