"""Agent trace entry: a set of Codex / Claude Code / generic agent trace files (formats in `knosis.data.traces`).

scenario names this set of traces; `paths` gives files or globs (comma-separated). No tasks: knowledge extraction only, scoring the knowledge layer itself.
"""

from __future__ import annotations

import glob
from pathlib import Path

from ..dataset import Dataset
from ..traces import detect, read
from . import register

METRICS = {
    "cites_trace": "fraction of active units citing a trace step (`data/traces/<id>.json#step/<n>`, step exists)",
    "env_verified": "fraction of active units with supporting evidence from the environment (data inspection / tool / executable check), not just trace restatement",
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
