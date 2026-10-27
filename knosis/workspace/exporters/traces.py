"""Agent traces: normalized to ATIF in `data/traces/<id>.json` (plus `.md`); optionally put the traces' environment (data directory) in `data/env/` for verification."""

from __future__ import annotations

import sys
from pathlib import Path

from ...data.traces import calls, dump, normalize, render as render_trace, warning
from ... import lang
from . import place, register, render


def describe(name, t) -> str:
    """The BRIEF line describing one trace."""
    subs = len(t.get("subagent_trajectories", []))
    fmt = t.get("extra", {}).get("knosis", {}).get("format", "")
    return lang.t(f"- `data/traces/{name}.json` (`.md` for reading): {fmt} trace, {len(t['steps'])} steps, {calls(t)} tool calls"
                  + (f", {subs} subagents" if subs else ""),
                  f"- `data/traces/{name}.json`（`.md` 便于阅读）：{fmt} 轨迹，{len(t['steps'])} 步，工具调用 {calls(t)} 次"
                  + (f"，子 agent {subs} 个" if subs else ""))


def brief(scenario, lines, n_env=None) -> str:
    env_note = (lang.t(f"`data/env/` is the environment data these traces faced at the time ({n_env} files, read-only): you can re-check the traces' claims against it.",
                       f"`data/env/` 是这些轨迹当时面对的环境数据（{n_env} 个文件，只读）：可以在上面重新检查轨迹里的说法。")
                if n_env is not None else
                lang.t("The traces' environment at the time is not provided: rely on the traces alone; claims that cannot be re-checked stay inferred.",
                       "没有提供轨迹当时的环境，只能依据轨迹本身；无法复核的说法保持 inferred。"))
    return render("traces.md", name=scenario, n_traces=len(lines), listing="\n".join(lines), env=env_note)


@register("traces")
def export(ds, ws: Path, write_data=True, env=None, modalities="trace", **opts) -> dict:
    """`env`: the data directory the traces worked on, copied as is into `data/env/` (read-only, for verifying claims in the traces); without it, extraction relies on the traces alone."""
    ws = Path(ws)
    lines = []
    for name, path in ds.files.items():
        t = normalize(path)
        if write_data:
            out = dump(t, ws / "data/traces" / f"{name}.json")
            out.with_suffix(".md").write_text(render_trace(t, name), encoding="utf-8")
            if warning(t):
                print(f"warning: {path}: {warning(t)}", file=sys.stderr)
        lines.append(describe(name, t))
    files = []
    if env:
        env = Path(env).expanduser().resolve()
        files = sorted(p for p in env.rglob("*") if p.is_file())
        if write_data:
            for p in files:
                place(p, ws / "data/env" / p.relative_to(env))
    return {
        "brief": brief(ds.scenario, lines, len(files) if env else None),
        "tasks": [], "dev": [], "holdout": [], "output": None,
        "modalities": [m for m in str(modalities).split(",") if m],
    }
