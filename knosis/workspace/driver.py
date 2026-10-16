"""驱动模式：由 Knosis 启动外部编码 agent（`codex exec` / `claude -p`）逐阶段完成并验收。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from ..knowledge import feedback, load_units
from . import check, goto, next_prompt, save_state, stage_dir, stage_issues, status


def agent_command(agent, ws, prompt, model=None):
    if agent == "codex":
        return ["codex", "exec", "-C", str(ws), "--sandbox", "workspace-write", "--skip-git-repo-check",
                *(["-m", model] if model else []), prompt]
    if agent == "claude":
        return ["claude", "-p", prompt, "--permission-mode", "acceptEdits", *(["--model", model] if model else []),
                "--allowedTools", "Bash", "Read", "Edit", "Write"]
    raise ValueError(f"unknown agent: {agent}")


def submit_round(ws, state, directory) -> None:
    """自动 RSI：refine 每轮结束时，把本轮的 dev 预测提交一次反馈，结果进入下一轮的提示。"""
    path = directory / f"dev_{state['output']}"
    submitted = {r["submitted"] for r in feedback.records(ws)}
    if path.exists() and str(path.relative_to(ws)) not in submitted and feedback.left(ws, state) > 0:
        feedback.submit(ws, path)


def run(ws, agent="codex", stages=None, rounds=1, model=None) -> None:
    """每阶段失败后带着验收问题重试一次；记录写入 `.knosis/runs.jsonl`。"""
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("nested agent runs are disabled (KNOSIS_DEPTH >= 1)")
    ws = Path(ws).resolve()
    env = {**os.environ, "KNOSIS_DEPTH": "1"}
    for stage in stages or ["explore", "extract"]:
        goto(ws, stage)
        for _ in range(rounds if stage == "refine" else 1):
            prompt = next_prompt(ws) + "\n驱动模式：由运行器验收和提交，不要自行运行 ws check 或切换阶段。"
            directory = stage_dir(ws, status(ws))
            issues = []
            for attempt in range(2):
                started = time.monotonic()
                before = status(ws)
                with (directory / "agent.log").open("a", encoding="utf-8") as log:
                    # stdin 必须关掉：codex exec 在 stdin 未关闭时会一直等待追加输入。
                    result = subprocess.run(agent_command(agent, ws, prompt, model), cwd=ws, env=env,
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
                          "agent": agent, "model": model, "seconds": time.monotonic() - started,
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
