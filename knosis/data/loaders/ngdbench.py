"""NGDBench：大规模属性图问答，结构化域自带 clean / perturbed 配对图。

    data/ngdbench/NGDBenchV1_1/<NGDFin|NGDBi|...>/{graph,query,noise_info}/
"""

from __future__ import annotations

import json
from pathlib import Path

from ..dataset import Dataset, Task, data_dir
from . import register

DOMAINS = ("ngd-bi", "ngd-fin", "ngd-prime", "ngd-mcp", "ngd-econ")

METRICS = {
    "answer_set_em": "答案集合与 GT 完全一致的比例（按 Cypher 返回别名做集合匹配，忽略顺序）",
    "answer_set_f1": "答案集合 F1",
    "count_error": "聚合题的计数相对误差（越低越好）",
    "management_steps": "管理类题按序执行 steps 的完成比例",
    "noise_sensitivity": "同一题在 perturbed 与 clean 图上的分差",
}


@register("ngdbench", scenarios=DOMAINS)
def load(scenario: str = "ngd-fin", root: str | Path | None = None, version: str = "NGDBenchV1_1") -> Dataset:
    vdir = Path(root or data_dir("ngdbench")) / version
    key = scenario.lower().replace("-", "")
    ddir = next(p for p in vdir.iterdir() if p.name.lower() == key)  # 磁盘目录名大小写不统一

    files = {}
    for p in sorted((ddir / "graph").iterdir()):
        if p.suffix in (".gpickle", ".graphml"):
            files["perturbed" if "_noise_" in p.name else "clean"] = p
    for sub in ("noise_info", "kg_extraction"):
        if (ddir / sub).is_dir():
            files[sub] = ddir / sub

    tasks = []
    for qfile in sorted((ddir / "query").glob("*.json")):
        if qfile.with_name(f"{qfile.stem}_with_nlp.json").is_file():  # NGD-MCP：同一批题另有带 NL 的版本
            continue
        for i, rec in enumerate(json.loads(qfile.read_text())):
            answer = next((rec.pop(k) for k in ("clean_answer", "gnd", "answer") if k in rec), None)
            tasks.append(Task(
                id=f"{scenario}/{qfile.stem}/{i}",
                input=rec.get("nlp") or rec.get("query") or json.dumps(rec.get("steps"), ensure_ascii=False),
                answer=answer,
                kind=qfile.stem,
                meta=rec,  # 含 Cypher（query）与 noise_answer
            ))

    return Dataset("ngdbench", scenario, ddir, files=files, tasks=tasks, metrics=METRICS)
