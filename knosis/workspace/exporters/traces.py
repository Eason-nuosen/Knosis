"""agent 轨迹：统一成步骤序列放进 `data/traces/`；可选把轨迹所在的环境（数据目录）放进 `data/env/` 供验证。"""

from __future__ import annotations

import json
from pathlib import Path

from ...data.traces import normalize, render as render_trace
from . import place, register, render


@register("traces")
def export(ds, ws: Path, write_data=True, env=None, modalities="trace", **opts) -> dict:
    """`env`：轨迹当时面对的数据目录，原样放进 `data/env/`（只读，用来验证轨迹里的说法）；不给则只能从轨迹本身提取。"""
    ws = Path(ws)
    lines = []
    for name, path in ds.files.items():
        steps = normalize(path)
        if write_data:
            out = ws / "data/traces" / f"{name}.jsonl"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in steps), encoding="utf-8")
            out.with_suffix(".md").write_text(render_trace(steps, name), encoding="utf-8")
        calls = sum(s["kind"] == "call" for s in steps)
        lines.append(f"- `data/traces/{name}.jsonl`（与 `.md` 同内容）：{ds.schema['formats'][name]} 轨迹，{len(steps)} 步，其中工具调用 {calls} 次")
    files = []
    if env:
        env = Path(env).expanduser().resolve()
        files = sorted(p for p in env.rglob("*") if p.is_file())
        if write_data:
            for p in files:
                place(p, ws / "data/env" / p.relative_to(env))
    env_note = (f"`data/env/` 是这些轨迹当时面对的环境数据（{len(files)} 个文件，只读）：可以在上面重新检查轨迹里的说法。"
                if env else "没有提供轨迹当时的环境，只能依据轨迹本身；无法复核的说法保持 inferred。")
    return {
        "brief": render("traces.md", name=ds.scenario, n_traces=len(ds.files), listing="\n".join(lines), env=env_note),
        "tasks": [], "dev": [], "holdout": [], "output": None,
        "modalities": [m for m in str(modalities).split(",") if m],
    }
