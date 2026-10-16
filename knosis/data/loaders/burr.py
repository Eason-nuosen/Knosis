"""Burr：从关系库 schema 写出到本体的映射。GT 是 mapping 文件，只放在 tasks 里。

    data/burr/micro_benchmark/<类别>/<子类>/<场景>/{schema.sql, mapping.json, *.csv}
    data/burr/real-world/<库>/{*.sql, mappings/*.json | *.ttl}
"""

from __future__ import annotations

from pathlib import Path

from ..dataset import Dataset, Task, data_dir
from . import register

REAL_WORLD = {
    "mondial": "real-world/mondial",
    "npd": "real-world/npd_factpages",
    "iswc": "real-world/iswc",
    "rba": "real-world/rba",
}

METRICS = {
    f"{family}_{kind}_{m}": f"{family}-based {kind} {m}"
    for family in ("mapping", "lexical")
    for kind in ("class", "relation", "attribute")
    for m in ("precision", "recall", "f1")
}


def scenarios(root: str | Path | None = None) -> list[str]:
    micro = Path(root or data_dir("burr")) / "micro_benchmark"
    return list(REAL_WORLD) + sorted(p.parent.relative_to(micro).as_posix() for p in micro.rglob("mapping.json"))


@register("burr", scenarios=scenarios)
def load(scenario: str = "mondial", root: str | Path | None = None) -> Dataset:
    base = Path(root or data_dir("burr"))
    sdir = base / REAL_WORLD.get(scenario, f"micro_benchmark/{scenario}")

    sqls = sorted(sdir.glob("*.sql"), key=lambda p: p.stat().st_size)
    # 真实库常同时给「纯 schema」与「schema + 实例数据」两份 SQL，DDL 取小的那份
    ddl_file = next((p for p in sqls if "schema" in p.name or "create" in p.name), sqls[0] if sqls else None)
    files = {p.name: p for p in sorted(sdir.iterdir()) if p.suffix in (".sql", ".csv")}

    gold = [sdir / "mapping.json"] if (sdir / "mapping.json").is_file() else (
        sorted(p for p in (sdir / "mappings").glob("*.json") if p.name != "meta.json") or sorted(sdir.glob("*.ttl"))
    )
    ddl = ddl_file.read_text(errors="replace") if ddl_file else ""
    task = Task(id=f"burr/{scenario}", input=ddl, answer=gold[0] if len(gold) == 1 else gold, kind="ontology_mapping")

    return Dataset("burr", scenario, sdir, files=files, schema={"ddl": ddl}, tasks=[task], metrics=METRICS)
