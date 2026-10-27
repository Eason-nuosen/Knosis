"""Burr: write a mapping from a relational schema to an ontology. GT is the mapping file, kept only in tasks.

    data/burr/micro_benchmark/<category>/<subcategory>/<scenario>/{schema.sql, mapping.json, *.csv}
    data/burr/real-world/<database>/{*.sql, mappings/*.json | *.ttl}

scenario is a real-world database name, a single micro scenario (`basic/table/person`), or a group of micro scenarios:
`micro` (all 54) or `micro/<category>` (e.g. `micro/basic`); one task per scenario, files keyed `<scenario>/<file name>`.
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
    singles = sorted(p.parent.relative_to(micro).as_posix() for p in micro.rglob("mapping.json"))
    groups = ["micro"] + sorted({f"micro/{s.split('/')[0]}" for s in singles})
    return list(REAL_WORLD) + groups + singles


@register("burr", scenarios=scenarios)
def load(scenario: str = "mondial", root: str | Path | None = None) -> Dataset:
    base = Path(root or data_dir("burr"))
    if scenario == "micro" or scenario.startswith("micro/"):
        micro = base / "micro_benchmark"
        group = micro / scenario.removeprefix("micro").strip("/")
        parts = [load(p.parent.relative_to(micro).as_posix(), root) for p in sorted(group.rglob("mapping.json"))]
        files = {f"{part.scenario}/{k}": v for part in parts for k, v in part.files.items()}
        return Dataset("burr", scenario, group, files=files, tasks=[t for part in parts for t in part.tasks], metrics=METRICS)
    sdir = base / REAL_WORLD.get(scenario, f"micro_benchmark/{scenario}")

    sqls = sorted(sdir.glob("*.sql"), key=lambda p: p.stat().st_size)
    # real-world databases often ship both a schema-only and a schema + data SQL file; take the smaller one as DDL
    ddl_file = next((p for p in sqls if "schema" in p.name or "create" in p.name), sqls[0] if sqls else None)
    files = {p.name: p for p in sorted(sdir.iterdir()) if p.suffix in (".sql", ".csv")}

    gold = [sdir / "mapping.json"] if (sdir / "mapping.json").is_file() else (
        sorted(p for p in (sdir / "mappings").glob("*.json") if p.name != "meta.json") or sorted(sdir.glob("*.ttl"))
    )
    ddl = ddl_file.read_text(errors="replace") if ddl_file else ""
    task = Task(id=f"burr/{scenario}", input=ddl, answer=gold[0] if len(gold) == 1 else gold, kind="ontology_mapping")

    return Dataset("burr", scenario, sdir, files=files, schema={"ddl": ddl}, tasks=[task], metrics=METRICS)
