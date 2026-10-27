"""Driver mode: Knosis launches an external coding agent (`codex exec` / `claude -p`) to complete each stage, then runs the acceptance check."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from ..lang import t
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
    """Automatic RSI: at the end of each refine round, submit this round's dev predictions for feedback; the result goes into the next round's prompt."""
    path = directory / f"dev_{state['output']}"
    submitted = {r["submitted"] for r in feedback.own(ws)}
    if path.exists() and str(path.relative_to(ws)) not in submitted and feedback.left(ws, state) > 0:
        dev = {t["id"] for t in load_units(ws / "tasks/dev.jsonl")}
        ids, _ = prediction_ids(path)
        # When full coverage is required, an incomplete file is not submitted; the acceptance check reports missing tasks and the stage is retried with those issues.
        if not state["feedback"].get("full") or dev <= set(ids):
            feedback.submit(ws, path)


def organize(path, agent="codex", model=None, effort=None) -> list[str]:
    """Run only the "build knowledge structure" step of consolidation (see `knowledge.consolidate`); return the final issue list."""
    from ..knowledge import consolidate

    return consolidate.run(path, ["organize"], agent, model, effort)[0]["issues"]


def run(ws, agent="codex", stages=None, rounds=1, model=None, effort=None, note=None, consolidate=False) -> None:
    """Each failed stage is retried once with the acceptance issues; runs are logged to `.knosis/runs.jsonl`. `note`: experiment instructions appended to every stage prompt.
    `consolidate`: after all refine rounds and before decide, run consolidation once (dedup -> contradiction handling -> build knowledge structure),
    then snapshot the knowledge layer again as the version after the last round."""
    if int(os.environ.get("KNOSIS_DEPTH", "0")) >= 1:
        raise RuntimeError("nested agent runs are disabled (KNOSIS_DEPTH >= 1)")
    ws = Path(ws).resolve()
    env = {**os.environ, "KNOSIS_DEPTH": "1"}
    for stage in stages or ["explore", "extract"]:
        goto(ws, stage)
        for _ in range(rounds if stage == "refine" else 1):
            prompt = next_prompt(ws) + (t(f"\n\n## Additional requirements for this experiment\n\n{note}\n",
                                          f"\n\n## 本次实验的附加要求\n\n{note}\n") if note else "") + \
                t("\nDriver mode: the runner checks and commits; do not run ws check yourself or switch stages.",
                  "\n驱动模式：由运行器验收和提交，不要自行运行 ws check 或切换阶段。")
            directory = stage_dir(ws, status(ws))
            issues = []
            for attempt in range(2):
                started = time.monotonic()
                before = status(ws)
                with (directory / "agent.log").open("a", encoding="utf-8") as log:
                    # stdin must be closed: codex exec keeps waiting for more input while stdin is open.
                    result = subprocess.run(agent_command(agent, ws, prompt, model, effort), cwd=ws, env=env,
                                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
                if result.returncode:
                    raise RuntimeError(f"{agent} exited with {result.returncode}; see {directory / 'agent.log'}")
                if stage == "refine":
                    submit_round(ws, before, directory)
                # The agent sometimes runs the check itself; still check the original stage's deliverables so switching state cannot bypass acceptance.
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
                prompt += t("\nAcceptance check failed, please fix:\n", "\n验收未通过，请修正：\n") + "\n".join(issues)
            if issues:
                raise RuntimeError("\n".join(issues))
        if stage == "refine":
            if consolidate:
                consolidate_ws(ws, agent, model, effort)
            goto(ws, "decide")


def consolidate_ws(ws, agent, model, effort) -> None:
    """Consolidation after refine; results and timing go to runs.jsonl. Passing steps change the knowledge layer, which is committed once more as a refine version (K_final)."""
    from ..knowledge import consolidate

    results = consolidate.run(ws, agent=agent, model=model, effort=effort)
    with (ws / ".knosis/runs.jsonl").open("a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps({"stage": "consolidate", **r, "agent": agent, "model": model, "effort": effort,
                                 "units": len(load_units(layout(ws).units))}, ensure_ascii=False) + "\n")
    if any(not r["issues"] for r in results):
        # Consolidation happens after the last refine round: snapshot as the next refine version (K_final); each step was already checked.
        from . import commit, copy_knowledge

        state = status(ws)
        state["stage"] = "refine"
        directory = stage_dir(ws, state)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "changelog.md").write_text(t("# Consolidation\n\n", "# 内化\n\n") + "\n".join(
            t(f"- {r['step']}: {'passed' if not r['issues'] else 'failed, reverted'}, actions {json.dumps(r.get('actions', {}), ensure_ascii=False)}",
              f"- {r['step']}：{'通过' if not r['issues'] else '未通过，已恢复'}，操作 {json.dumps(r.get('actions', {}), ensure_ascii=False)}")
            for r in results) + "\n", encoding="utf-8")
        copy_knowledge(ws, directory)
        state["round"] += 1
        save_state(ws, state)
        commit(ws, f"consolidate: {len(load_units(layout(ws).units))} units")
