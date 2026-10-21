"""agent 轨迹入口：一组 Codex / Claude Code / 普通 agent 的轨迹文件（格式见 `knosis.data.traces`）。

scenario 是这组轨迹的名字；`paths` 给文件或 glob（逗号分隔）。没有题目：只做知识提取，评知识层本身。
"""

from __future__ import annotations

import glob
from pathlib import Path

from ..dataset import Dataset
from ..traces import detect, read
from . import register

METRICS = {
    "cites_trace": "引用了轨迹步骤（`data/traces/<id>.jsonl#step/<n>`，且步骤存在）的活跃单元比例",
    "env_verified": "有来自环境（数据检查 / 工具 / 可执行检查）的支持证据、而不只是轨迹转述的活跃单元比例",
}


@register("traces")
def load(scenario: str = "traces", paths: str = "", root: str | Path | None = None) -> Dataset:
    files = {}
    for pattern in str(paths).split(","):
        for p in sorted(glob.glob(str(Path(pattern.strip()).expanduser()))):
            p = Path(p)
            files[p.stem] = p
    formats = {k: detect(read(p)) for k, p in files.items()}
    return Dataset("traces", scenario, Path(root or "."), files=files, schema={"formats": formats}, metrics=METRICS)
