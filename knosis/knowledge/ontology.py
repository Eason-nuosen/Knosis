"""本体子层：Apache Ossie 三文件格式（core / ontology / mapping）+ EOB 扩展，与 ontology-bench 同一格式。

一份本体是一个目录下的至多三个文件：

    <name>.semantic_model.yaml   core：表、列、主键、join、度量
    <name>.ontology.yaml         概念、概念间关系、单位与约束（不提表和列）
    <name>.mapping.yaml          列 → 概念 / 关系

本体是知识层里的结构部分：κ 单元用 `about` 字段引用本体元素（`refs` 给出可引用的名字），
`ontology_units` 把本体元素展开成 `form=schema` 的 κ，供只认 κ 的下游统一使用。
EOB 信息写在 `custom_extensions`（`vendor_name: EOB`，`data` 是 JSON 字符串），不改官方 schema。
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
# EOB provenance.method / 元素 origin → κ 的 status
STATUS_BY_METHOD = {"human": "verified", "annotator": "verified", "converted": "observed", "llm": "inferred", "tool": "inferred"}
STATUS_BY_ORIGIN = {**STATUS_BY_METHOD, "inferred": "inferred"}

# 来自 benchmark GT、不能给被测 agent 的东西（relbench_gt 除外：RelBench 的 brief 本来就给 schema）
GT_ORIGINS = {"pbi_gt", "bibench_transformation_gt", "bibench_transformation_output"}
GT_PREFIX = ("bibench_",)
# 提到这些就等于泄露了逐题 oracle
ORACLE_MARKS = ("query_metadata", "transformation/", "transformation\\")
# 行首的 annotator 标记（`source` / 根 EOB 的 `note`）
NOTE_MARKERS = ("annotator-only", "annotator only")
SQL = re.compile(r"^\s*(SELECT|WITH)\b", re.I)


def load_ontology(directory) -> dict[str, dict]:
    """返回 {层名: 文档}；缺的层不出现。一个目录只放一份本体。"""
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
    """合并一个条目上所有 EOB 扩展的 data。"""
    merged = {}
    for ext in item.get("custom_extensions") or []:
        if ext.get("vendor_name") == "EOB":
            merged.update(json.loads(ext["data"]))
    return merged


def refs(docs: dict[str, dict]) -> set[str]:
    """可被 κ 的 `about` 引用的名字：dataset、`dataset.field`、core relationship 名、metric 名、
    概念名、`概念.关系名`。"""
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
    """跨文件引用检查（官方 validate.py 不查的部分）；返回问题清单。"""
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


def ontology_units(docs: dict[str, dict], prefix: str = "knowledge/ontology") -> list[dict]:
    """把本体元素展开成 κ（form=schema）。status 优先取元素上的 `origin`，其次 EOB provenance.method，默认 observed。"""
    units = []
    # ontology 层不允许 custom_extensions，整份本体的 provenance 记在 core / mapping 的根上。
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
    """dataset 的来源短描述：SQL 视图只记标记，不把整段 SQL（往往是 GT 变换的复现）塞进 κ。"""
    source = ds.get("source", "")
    return "（SQL 视图）" if SQL.match(source) else source


# ---------------------------------------------------------------- 剔除 benchmark GT


def strip_gt(docs: dict[str, dict]) -> tuple[dict[str, dict], dict]:
    """去掉来自 benchmark GT 的部分（关系 / 条目的 origin 是 pbi_gt、bibench_*，以及被 SQL 或 oracle 变换
    复现出来的 dataset 及其全部引用），返回 (新文档, 各类计数)。relbench_gt 与 annotator 的内容保留。

    返回的计数按元素数；连到 transient 表（LocalDateTable_…）的 GT 关系没有 dataset 可数，记在 `dataset` 下。
    根 provenance 一律改成 `{"method": "llm"}`（内容已不再是标注者照 GT 抄的），有剔除时加 `stripped` 明细。
    `origin: annotator` 的度量与注记（从数据推出的）保留，只把提到 oracle 的根注记换成占位。
    """
    report = dict.fromkeys(("relationship", "dataset", "metric", "mapping", "annotation", "transform", "note"), 0)
    docs = copy.deepcopy(docs)
    model = docs.get("semantic_model", {})
    dropped = {ds["name"] for ds in model.get("datasets", []) if is_oracle(ds)}
    report["dataset"] = len(dropped)
    if dropped:
        model["datasets"] = [ds for ds in model.get("datasets", []) if ds["name"] not in dropped]
        # 只连到 transient 表（LocalDateTable_…）的 GT 关系：那些表本就不在 datasets 里，记到 dataset 一栏。
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
    """dataset 是否由 GT 的逐题变换（query_metadata / transformation/）复现而来：SQL 视图，
    或其描述 / EOB note 明说是 GT 变换的产物，或带 GT 来源的变换步骤。"""
    ext = eob_data(ds)
    # BI-Bench 的 SQL 视图都是按 query_metadata 复现的逐题变换；KramaBench 等的视图是标注者对原始文件的拆分 / 派生，不是 GT。
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
    """条目里是否引用了这些 dataset（`表` 或 `表.列`，也认 SQL 表达式里出现的表名）。"""
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
    """根 EOB 的 note / source.note 提到 oracle 或标注为 annotator 专用时换成占位。"""
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
    """把 EOB 扩展整体换成 `data`（其余扩展不动）。"""
    item["custom_extensions"] = [x for x in item.get("custom_extensions") or [] if x.get("vendor_name") != "EOB"] + eob(data)


def import_annotation(src_dir, dest_dir, strip: bool = False) -> dict:
    """把一个标注单元的三个 yaml（不要 report.md）复制到 `<dest_dir>/<单元名>/`，返回剔除报告。

    `dest_dir` 是知识层的 `ontology/` 目录：每个单元一个子目录，多个单元可以共存。
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


# ---------------------------------------------------------------- core 层的构造与转换


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
    """由 {表名: DataFrame 或 {列名: datatype}} 构造 core 层。表名保留为 `source`，dataset 名转成 snake_case。"""
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


# Power BI（TOM）的 DataType 编码
POWERBI_TYPES = {2: "String", 6: "Integer", 8: "Float", 9: "DateTime", 10: "Decimal", 11: "Boolean"}
CARDINALITY = {1: "one", 2: "many"}


def from_bibench(ds) -> dict:
    """BI-Bench 用例的 Power BI 模型元数据 → core 层。

    注意：`_relationships` 是项目作者定义的关系，在 join 发现类评测里属于 GT，不应给被测 agent。
    """
    import pandas as pd

    tables = pd.read_csv(ds.files["_tables"])
    columns = pd.read_csv(ds.files["_columns"])
    rels = pd.read_csv(ds.files["_relationships"])
    # Power BI 自动生成的日期表与 RowNumber 列不是用户数据。
    tables = tables[~tables["Name"].str.startswith(("LocalDateTable_", "DateTableTemplate_"))]
    columns = columns[(columns["Type"] != 3) & columns["TableID"].isin(tables["ID"])].copy()
    columns["name"] = columns["ExplicitName"].fillna(columns["InferredName"])
    columns["datatype"] = [
        POWERBI_TYPES.get(e if e != 1 else i, "String")
        for e, i in zip(columns["ExplicitDataType"], columns["InferredDataType"])
    ]
    table_names = dict(zip(tables["ID"], tables["Name"]))
    col_names = dict(zip(columns["ID"], columns["name"]))
    # 不同表名可能转成同一个 snake 名（"Table (5)" 与 "Table 5"），重名时加序号。
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
        (ft, fc), (tt, tc) = (a, b) if many_from else (b, a)  # Ossie 的 from 是多的一侧
        relationships.append(relationship(
            dataset_names[ft], [col_names[fc]], dataset_names[tt], [col_names[tc]],
            cardinality=f"{CARDINALITY[r.FromCardinality]}-to-{CARDINALITY[r.ToCardinality]}",
            active=bool(r.IsActive), cross_filter={1: "single", 2: "both"}.get(r.CrossFilteringBehavior, "none"),
        ))
    return semantic_model(f"bibench_{ds.scenario}", datasets, relationships,
                          provenance={"method": "converted", "author": "knosis.from_bibench"},
                          source={"dataset": "bi-bench", "item": ds.scenario})


def from_relbench(ds) -> dict:
    """RelBench 库的 manifest（pkey / fkeys / time_col）+ parquet 列类型 → core 层。"""
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
