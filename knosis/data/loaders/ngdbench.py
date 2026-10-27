"""NGDBench: QA over large property graphs; structured domains come with paired clean / perturbed graphs.

    data/ngdbench/NGDBenchV1_1/<NGDFin|NGDBi|...>/{graph,query,noise_info}/
"""

from __future__ import annotations

import json
from pathlib import Path

from ..dataset import Dataset, Task, data_dir
from . import register

DOMAINS = ("ngd-bi", "ngd-fin", "ngd-prime", "ngd-mcp", "ngd-econ")

METRICS = {
    "answer_set_em": "fraction whose answer set equals the GT exactly (set match on Cypher return aliases, order ignored)",
    "answer_set_f1": "answer set F1",
    "count_error": "relative count error on aggregation questions (lower is better)",
    "management_steps": "fraction of steps completed in order on management questions",
    "noise_sensitivity": "score gap on the same question between perturbed and clean graphs",
}


@register("ngdbench", scenarios=DOMAINS)
def load(scenario: str = "ngd-fin", root: str | Path | None = None, version: str = "NGDBenchV1_1") -> Dataset:
    vdir = Path(root or data_dir("ngdbench")) / version
    key = scenario.lower().replace("-", "")
    ddir = next(p for p in vdir.iterdir() if p.name.lower() == key)  # directory name casing on disk is inconsistent

    files = {}
    for p in sorted((ddir / "graph").iterdir()):
        if p.suffix in (".gpickle", ".graphml"):
            files["perturbed" if "_noise_" in p.name else "clean"] = p
    for sub in ("noise_info", "kg_extraction"):
        if (ddir / sub).is_dir():
            files[sub] = ddir / sub

    tasks = []
    for qfile in sorted((ddir / "query").glob("*.json")):
        if qfile.with_name(f"{qfile.stem}_with_nlp.json").is_file():  # NGD-MCP: the same questions also have a version with NL
            continue
        for i, rec in enumerate(json.loads(qfile.read_text())):
            answer = next((rec.pop(k) for k in ("clean_answer", "gnd", "answer") if k in rec), None)
            tasks.append(Task(
                id=f"{scenario}/{qfile.stem}/{i}",
                input=rec.get("nlp") or rec.get("query") or json.dumps(rec.get("steps"), ensure_ascii=False),
                answer=answer,
                kind=qfile.stem,
                meta=rec,  # includes Cypher (query) and noise_answer
            ))

    return Dataset("ngdbench", scenario, ddir, files=files, tasks=tasks, metrics=METRICS)
