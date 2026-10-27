"""Ontology sublayer: Apache Ossie three-file format (core / ontology / mapping) + EOB extensions, same format as ontology-bench.

An ontology is up to three files in one directory:

    <name>.semantic_model.yaml   core: tables, columns, primary keys, joins, metrics
    <name>.ontology.yaml         concepts, relations between concepts, units and constraints (no tables or columns)
    <name>.mapping.yaml          columns -> concepts / relations

The ontology is the structural part of the knowledge layer: κ units reference ontology elements via `about` (`refs` gives the citable names);
`ontology_units` expands ontology elements into `form=schema` κ for downstream code that only understands κ.
EOB information lives in `custom_extensions` (`vendor_name: EOB`, `data` is a JSON string), leaving the official schema untouched.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import yaml

VERSION = "0.2.0.dev0"
EOB_VERSION = "0.2"
LAYERS = ("semantic_model", "ontology", "mapping")
BUILTIN_TYPES = {"String", "Integer", "Decimal", "Float", "Boolean", "Date", "Time", "DateTime", "DateTimeTz", "Opaque", "Any"}
# EOB provenance.method / element origin -> κ status
STATUS_BY_METHOD = {"human": "verified", "annotator": "verified", "converted": "observed", "llm": "inferred", "tool": "inferred"}
STATUS_BY_ORIGIN = {**STATUS_BY_METHOD, "inferred": "inferred"}

# from benchmark GT and must not reach the agent under test (except relbench_gt: RelBench's brief already gives the schema)
GT_ORIGINS = {"pbi_gt", "bibench_transformation_gt", "bibench_transformation_output"}
GT_PREFIX = ("bibench_",)
# mentioning these leaks the per-question oracle
ORACLE_MARKS = ("query_metadata", "transformation/", "transformation\\")
# leading annotator marker (`source` / root EOB `note`)
NOTE_MARKERS = ("annotator-only", "annotator only")
SQL = re.compile(r"^\s*(SELECT|WITH)\b", re.I)


def load_ontology(directory) -> dict[str, dict]:
    """Return {layer name: document}; missing layers are omitted. One ontology per directory."""
    docs = {}
    for layer in LAYERS:
        paths = sorted(Path(directory).glob(f"*.{layer}.yaml"))
        if paths:
            [path] = paths
            docs[layer] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return docs


def write_ontology(directory, docs: dict[str, dict]) -> list[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name = docs["semantic_model"]["name"] if "semantic_model" in docs else docs["ontology"]["name"]
    paths = []
    for layer, doc in docs.items():
        path = directory / f"{name}.{layer}.yaml"
        path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
        paths.append(path)
    return paths


def eob(data: dict) -> list[dict]:
    return [{"vendor_name": "EOB", "data": json.dumps(data, ensure_ascii=False)}]


def eob_data(item: dict) -> dict:
    """Merge the data of all EOB extensions on an entry."""
    merged = {}
    for ext in item.get("custom_extensions") or []:
        if ext.get("vendor_name") == "EOB":
            merged.update(json.loads(ext["data"]))
    return merged


def refs(docs: dict[str, dict]) -> set[str]:
    """Names citable by κ `about`: dataset, `dataset.field`, core relationship names, metric names,
    concept names, `concept.relation`."""
    names = set()
    model = docs.get("semantic_model", {})
    for ds in model.get("datasets", []):
        names.add(ds["name"])
        names.update(f"{ds['name']}.{f['name']}" for f in ds.get("fields", []))
    names.update(r["name"] for r in model.get("relationships", []))
    names.update(m["name"] for m in model.get("metrics", []))
    for concept in docs.get("ontology", {}).get("ontology", []):
        names.add(concept["concept"])
        names.update(f"{concept['concept']}.{r['name']}" for r in concept.get("relationships", []))
    return names


def check_ontology(docs: dict[str, dict]) -> list[str]:
    """Cross-file reference checks (what the official validate.py does not cover); return a list of issues."""
    issues = []
    model = docs.get("semantic_model", {})
    fields = {ds["name"]: {f["name"] for f in ds.get("fields", [])} for ds in model.get("datasets", [])}
    for r in model.get("relationships", []):
        for side, key in (("from", "from_columns"), ("to", "to_columns")):
            if r[side] not in fields:
                issues.append(f"relationship {r['name']}: unknown dataset {r[side]}")
                continue
            issues += [f"relationship {r['name']}: unknown field {r[side]}.{c}" for c in r[key] if c not in fields[r[side]]]
        if len(r["from_columns"]) != len(r["to_columns"]):
            issues.append(f"relationship {r['name']}: column count mismatch")

    concepts = {c["concept"]: c for c in docs.get("ontology", {}).get("ontology", [])}
    for c in concepts.values():
        for parent in c.get("extends", []):
            if parent not in concepts and parent not in BUILTIN_TYPES:
                issues.append(f"concept {c['concept']}: unknown parent {parent}")
        for r in c.get("relationships", []):
            issues += [f"relationship {c['concept']}.{r['name']}: unknown concept {role['concept']}"
                       for role in r.get("roles", []) if role["concept"] not in concepts and role["concept"] not in BUILTIN_TYPES]

    mapping = docs.get("mapping")
    if mapping:
        columns = {f"{d}.{f}" for d, fs in fields.items() for f in fs}
        names = refs(docs)
        for cm in mapping.get("concept_mappings", []):
            if cm["concept"] not in concepts:
                issues.append(f"mapping: unknown concept {cm['concept']}")
        for item in walk(mapping.get("concept_mappings", [])):
            if isinstance(item.get("expression"), str) and item["expression"] not in columns:
                issues.append(f"mapping: expression is not a dataset.field: {item['expression']}")
        for ann in eob_data(mapping).get("annotations", []):
            if ann.get("target") not in names:
                issues.append(f"mapping: annotation target not found: {ann.get('target')}")
    return issues


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def ontology_units(docs: dict[str, dict], prefix: str = "kb/knowledge/ontology") -> list[dict]:
    """Expand ontology elements into κ (form=schema). status comes from the element's `origin`, then EOB provenance.method, default observed."""
    units = []
    # the ontology layer forbids custom_extensions; provenance of the whole ontology is on the core / mapping root.
    default = next((eob_data(docs[k])["provenance"] for k in ("semantic_model", "mapping")
                    if k in docs and "provenance" in eob_data(docs[k])), {})

    def add(uid, content, path, location, item, root, about):
        ext = eob_data(item)
        method = (ext.get("provenance") or eob_data(root).get("provenance") or default).get("method")
        status = STATUS_BY_ORIGIN.get(ext.get("origin")) or STATUS_BY_METHOD.get(method, "observed")
        units.append({
            "id": f"ontology/{uid}", "content": content, "form": "schema",
            "provenance": f"{prefix}/{path}#{location}", "status": status,
            "about": [about], "meta": {"layer": path.split(".")[-2]},
        })

    model = docs.get("semantic_model")
    if model:
        path = f"{model['name']}.semantic_model.yaml"
        for ds in model.get("datasets", []):
            cols = ", ".join(f"{f['name']}:{f.get('datatype', '?')}" for f in ds.get("fields", []))
            key = f"；主键 {ds['primary_key']}" if ds.get("primary_key") else ""
            hint = (ds.get("ai_context") or {}).get("instructions", "")
            add(f"dataset/{ds['name']}", f"表 {ds['name']}（{source_text(ds)}）列 {cols}{key}" + (f"。{hint}" if hint else ""),
                path, f"dataset/{ds['name']}", ds, model, ds["name"])
        for r in model.get("relationships", []):
            content = f"{r['from']}({', '.join(r['from_columns'])}) → {r['to']}({', '.join(r['to_columns'])})"
            add(f"join/{r['name']}", f"join：{content}", path, f"relationship/{r['name']}", r, model, r["name"])
        for m in model.get("metrics", []):
            expr = m["expression"]["dialects"][0]["expression"]
            add(f"metric/{m['name']}", f"度量 {m['name']} = {expr}", path, f"metric/{m['name']}", m, model, m["name"])
    onto = docs.get("ontology")
    if onto:
        path = f"{onto['name']}.ontology.yaml"
        for c in onto.get("ontology", []):
            extends = f" extends {c['extends']}" if c.get("extends") else ""
            add(f"concept/{c['concept']}", f"{c['type']} {c['concept']}{extends}：{c.get('description', '')}".rstrip("："),
                path, f"concept/{c['concept']}", c, onto, c["concept"])
            for r in c.get("relationships", []):
                add(f"relation/{c['concept']}.{r['name']}", "; ".join(r.get("verbalizes", [])) or r["name"],
                    path, f"relationship/{c['concept']}.{r['name']}", r, onto, f"{c['concept']}.{r['name']}")
    return units


def source_text(ds: dict) -> str:
    """Short source description of a dataset: SQL views get only a marker, not the full SQL (often a reproduction of GT transformations) in κ."""
    source = ds.get("source", "")
    return "（SQL 视图）" if SQL.match(source) else source


# ---------------------------------------------------------------- strip benchmark GT


def strip_gt(docs: dict[str, dict]) -> tuple[dict[str, dict], dict]:
    """Remove parts from benchmark GT (relations / entries with origin pbi_gt, bibench_*, and datasets reproduced by SQL or oracle
    transformations together with all their references); return (new documents, counts by kind). relbench_gt and annotator content is kept.

    Counts are per element; GT relations to transient tables (LocalDateTable_…) have no dataset to count and are recorded under `dataset`.
    Root provenance always becomes `{"method": "llm"}` (content is no longer copied from GT by the annotator), plus `stripped` details when anything was removed.
    `origin: annotator` metrics and notes (derived from data) are kept; only root notes mentioning the oracle are replaced with a placeholder.
    """
    report = dict.fromkeys(("relationship", "dataset", "metric", "mapping", "annotation", "transform", "note"), 0)
    docs = copy.deepcopy(docs)
    model = docs.get("semantic_model", {})
    dropped = {ds["name"] for ds in model.get("datasets", []) if is_oracle(ds)}
    report["dataset"] = len(dropped)
    if dropped:
        model["datasets"] = [ds for ds in model.get("datasets", []) if ds["name"] not in dropped]
        # GT relations only to transient tables (LocalDateTable_…): those tables are not in datasets, so count them under dataset.
        names = {ds["name"] for ds in model["datasets"]}
        orphans = {side for r in model.get("relationships", []) if _forbidden(r) for side in (r["from"], r["to"])}
        orphans -= names
        dropped |= orphans
        report["dataset"] += len(orphans)
        model["relationships"] = [r for r in model.get("relationships", [])
                                  if r["from"] not in dropped and r["to"] not in dropped]

    for layer, doc in docs.items():
        report["relationship"] += _strip_list(doc, "relationships", lambda r: _forbidden(r) or mentions(r, dropped))
        report["metric"] += _strip_list(doc, "metrics", lambda r: _forbidden(r) or mentions(r, dropped))
        report["dataset"] += _strip_list(doc, "datasets", lambda r: _forbidden(r))
        root = eob_data(doc)
        for key in ("pbi_transforms", "bibench_transformations", "gt_transforms"):
            if key in root:
                report["transform"] += _strip_list(root, key, lambda r: _forbidden(r) or mentions(r, dropped))
        n = _strip_notes(root)
        report["note"] += n
        if n:
            _write_eob(doc, root)

    mapping = docs.get("mapping")
    if mapping:
        report["mapping"] += _strip_list(mapping, "concept_mappings", lambda cm: mentions(cm, dropped))
        ext = eob_data(mapping)
        for key in ("annotations", "conditional_mappings"):
            if key in ext:
                report["annotation" if key == "annotations" else "mapping"] += _strip_list(
                    ext, key, lambda x: mentions(x, dropped))
        _write_eob(mapping, ext)

    stripped = [f"{k}:{v}" for k, v in report.items() if v]
    for key in ("semantic_model", "mapping"):
        if key in docs:
            ext = eob_data(docs[key])
            ext["provenance"] = {"method": "llm", "stripped": stripped} if stripped else {"method": "llm"}
            _write_eob(docs[key], ext)
    return docs, report


def is_oracle(ds: dict) -> bool:
    """Whether a dataset was reproduced from GT per-question transformations (query_metadata / transformation/): a SQL view,
    or its description / EOB note says it comes from a GT transformation, or it has transformation steps with a GT source."""
    ext = eob_data(ds)
    # BI-Bench SQL views all reproduce per-question transformations from query_metadata; views in KramaBench etc. are annotator splits / derivations of raw files, not GT.
    other = str((ext.get("raw") or {}).get("path", "")).startswith(("kramabench", "relbench", "fdabench"))
    return (bool(SQL.match(ds.get("source", ""))) and not other
            or _text_hit(ds.get("description")) or _text_hit(ext.get("note"))
            or any(_forbidden(t) or _text_hit(t.get("note")) for t in ext.get("transforms", [])))


def _text_hit(value) -> bool:
    return isinstance(value, str) and any(mark in value for mark in ORACLE_MARKS)


def _forbidden(item: dict) -> bool:
    origin = eob_data(item).get("origin") if isinstance(item, dict) else None
    return bool(origin) and (origin in GT_ORIGINS or origin.startswith(GT_PREFIX))


def mentions(item, names: set[str]) -> bool:
    """Whether the entry references these datasets (`table` or `table.column`, including table names in SQL expressions)."""
    if not names or not isinstance(item, dict):
        return False
    values = []
    walk_dict(item, values)
    pattern = re.compile(rf"(?<![0-9A-Za-z_])({'|'.join(map(re.escape, sorted(names)))})(?![0-9A-Za-z_])")
    return any(isinstance(v, str) and pattern.search(v) for v in values)


def walk_dict(node, out):
    if isinstance(node, dict):
        out.extend(node.values())
        for value in node.values():
            walk_dict(value, out)
    elif isinstance(node, list):
        for value in node:
            walk_dict(value, out)


def _strip_list(node: dict, key: str, drop) -> int:
    items = node.get(key) or []
    kept = [x for x in items if not drop(x)]
    if len(kept) != len(items):
        node[key] = kept
    return len(items) - len(kept)


def _strip_notes(root: dict) -> int:
    """Replace root EOB note / source.note with a placeholder when it mentions the oracle or is marked annotator-only."""
    n = 0
    if isinstance(root.get("note"), str) and (_text_hit(root["note"]) or _annotator(root["note"])):
        root["note"] = "（提到被剔除的 GT 内容，见 provenance.stripped）"
        n += 1
    source = root.get("source")
    if isinstance(source, dict) and isinstance(source.get("note"), str) and (
            _text_hit(source["note"]) or _annotator(source["note"])):
        source["note"] = "（提到被剔除的 GT 内容，见 provenance.stripped）"
        n += 1
    return n


def _annotator(note: str) -> bool:
    return any(mark in note.lower() for mark in NOTE_MARKERS)


def _write_eob(item: dict, data: dict) -> None:
    """Replace the EOB extension wholesale with `data` (other extensions untouched)."""
    item["custom_extensions"] = [x for x in item.get("custom_extensions") or [] if x.get("vendor_name") != "EOB"] + eob(data)


def import_annotation(src_dir, dest_dir, strip: bool = False) -> dict:
    """Copy an annotation unit's three yaml files (not report.md) to `<dest_dir>/<unit name>/`; return the strip report.

    `dest_dir` is the knowledge layer's `ontology/` directory: one subdirectory per unit, so several units can coexist.
    """
    src = Path(src_dir)
    [model] = src.glob("*.semantic_model.yaml")
    name = model.name.removesuffix(".semantic_model.yaml")
    out = Path(dest_dir) / name
    out.mkdir(parents=True, exist_ok=True)
    (out / model.name).write_text(model.read_text(encoding="utf-8"), encoding="utf-8")
    for layer in ("ontology", "mapping"):
        [path] = src.glob(f"*.{layer}.yaml")
        (out / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    report = {"unit": name, "dir": str(out), "stripped": False}
    if strip:
        docs, counts = strip_gt(load_ontology(out))
        for path in out.glob("*.yaml"):
            path.unlink()
        write_ontology(out, docs)
        report |= {"stripped": True, "counts": counts}
    return report


# ---------------------------------------------------------------- building and converting the core layer


def snake(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower() or "t"


def datatype(dtype) -> str:
    import pandas as pd

    if pd.api.types.is_bool_dtype(dtype):
        return "Boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "Integer"
    if pd.api.types.is_float_dtype(dtype):
        return "Float"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "DateTime"
    return "String"


def field(name: str, dtype: str, dialect: str = "ANSI_SQL", expression: str | None = None) -> dict:
    return {"name": name, "expression": {"dialects": [{"dialect": dialect, "expression": expression or name}]},
            "datatype": dtype}


def relationship(from_ds, from_cols, to_ds, to_cols, **ext) -> dict:
    r = {"name": f"{from_ds}_{'_'.join(map(snake, from_cols))}_to_{to_ds}",
         "from": from_ds, "to": to_ds, "from_columns": list(from_cols), "to_columns": list(to_cols)}
    if ext:
        r["custom_extensions"] = eob(ext)
    return r


def semantic_model(name, datasets, relationships=(), provenance=None, source=None, description="") -> dict:
    ext = {"eob_version": EOB_VERSION}
    if source:
        ext["source"] = source
    if provenance:
        ext["provenance"] = provenance
    model = {"version": VERSION, "name": snake(name)}
    if description:
        model["description"] = description
    model["custom_extensions"] = eob(ext)
    model["datasets"] = list(datasets)
    if relationships:
        model["relationships"] = list(relationships)
    return model


def from_tables(name, tables: dict, primary_keys=None, relationships=(), provenance=None, source=None) -> dict:
    """Build a core layer from {table name: DataFrame or {column name: datatype}}. Table names are kept as `source`; dataset names become snake_case."""
    primary_keys = primary_keys or {}
    datasets = []
    for table, frame in tables.items():
        types = frame if isinstance(frame, dict) else {c: datatype(t) for c, t in frame.dtypes.items()}
        ds = {"name": snake(table), "source": table}
        if primary_keys.get(table):
            ds["primary_key"] = list(primary_keys[table])
        ds["fields"] = [field(c, t) for c, t in types.items()]
        datasets.append(ds)
    return semantic_model(name, datasets, relationships, provenance, source)


# Power BI (TOM) DataType codes
POWERBI_TYPES = {2: "String", 6: "Integer", 8: "Float", 9: "DateTime", 10: "Decimal", 11: "Boolean"}
CARDINALITY = {1: "one", 2: "many"}


def from_bibench(ds) -> dict:
    """Power BI model metadata of a BI-Bench case -> core layer.

    Note: `_relationships` are relations defined by the project author; in join-discovery evaluations they are GT and must not reach the agent under test.
    """
    import pandas as pd

    tables = pd.read_csv(ds.files["_tables"])
    columns = pd.read_csv(ds.files["_columns"])
    rels = pd.read_csv(ds.files["_relationships"])
    # Power BI auto-generated date tables and RowNumber columns are not user data.
    tables = tables[~tables["Name"].str.startswith(("LocalDateTable_", "DateTableTemplate_"))]
    columns = columns[(columns["Type"] != 3) & columns["TableID"].isin(tables["ID"])].copy()
    columns["name"] = columns["ExplicitName"].fillna(columns["InferredName"])
    columns["datatype"] = [
        POWERBI_TYPES.get(e if e != 1 else i, "String")
        for e, i in zip(columns["ExplicitDataType"], columns["InferredDataType"])
    ]
    table_names = dict(zip(tables["ID"], tables["Name"]))
    col_names = dict(zip(columns["ID"], columns["name"]))
    # different table names may map to the same snake name ("Table (5)" and "Table 5"); append a number on collision.
    dataset_names, used = {}, set()
    for tid, tname in table_names.items():
        name, n = snake(tname), 2
        while name in used:
            name, n = f"{snake(tname)}_{n}", n + 1
        used.add(name)
        dataset_names[tid] = name

    datasets = []
    for tid, tname in table_names.items():
        cols = columns[columns["TableID"] == tid]
        fields = [field(c.name, c.datatype) if pd.isna(c.Expression) else field(c.name, c.datatype, "DAX", c.Expression)
                  for c in cols.itertuples()]
        datasets.append({"name": dataset_names[tid], "source": tname, "fields": fields,
                         "custom_extensions": eob({"source_kind": "csv", "raw": {"path": f"{tname}.csv"}})})

    relationships = []
    for r in rels.itertuples():
        if r.FromColumnID not in col_names or r.ToColumnID not in col_names:
            continue
        many_from = r.FromCardinality == 2 or r.ToCardinality != 2
        a, b = ((r.FromTableID, r.FromColumnID), (r.ToTableID, r.ToColumnID))
        (ft, fc), (tt, tc) = (a, b) if many_from else (b, a)  # Ossie's from is the many side
        relationships.append(relationship(
            dataset_names[ft], [col_names[fc]], dataset_names[tt], [col_names[tc]],
            cardinality=f"{CARDINALITY[r.FromCardinality]}-to-{CARDINALITY[r.ToCardinality]}",
            active=bool(r.IsActive), cross_filter={1: "single", 2: "both"}.get(r.CrossFilteringBehavior, "none"),
        ))
    return semantic_model(f"bibench_{ds.scenario}", datasets, relationships,
                          provenance={"method": "converted", "author": "knosis.from_bibench"},
                          source={"dataset": "bi-bench", "item": ds.scenario})


def from_relbench(ds) -> dict:
    """RelBench database manifest (pkey / fkeys / time_col) + parquet column types -> core layer."""
    import pyarrow.parquet as pq

    tables, keys, relationships = {}, {}, []
    for table, spec in ds.schema["tables"].items():
        arrow = pq.read_schema(ds.files[table])
        tables[table] = {name: datatype(arrow.field(name).type.to_pandas_dtype()) for name in arrow.names}
        if spec.get("pkey"):
            keys[table] = [spec["pkey"]]
        for column, target in (spec.get("fkeys") or {}).items():
            relationships.append(relationship(snake(table), [column], snake(target), [ds.schema["tables"][target]["pkey"]]))
    model = from_tables(f"relbench_{ds.scenario}", tables, keys, relationships,
                        provenance={"method": "converted", "author": "knosis.from_relbench"},
                        source={"dataset": "relbench", "item": ds.scenario})
    for d in model["datasets"]:
        time_col = ds.schema["tables"][d["source"]].get("time_col")
        for f in d["fields"]:
            if f["name"] == time_col:
                f["dimension"] = {"is_time": True}
    return model
