"""Inclusion-dependency join discovery, optionally writing a draft ontology core layer."""

from __future__ import annotations

import argparse
import difflib
import time
from pathlib import Path

import pandas as pd

from knosis.knowledge import ontology
from knosis.tools import read_tables, write_result


def key_values(values: pd.Series) -> set[str] | None:
    """Value set usable for join comparison; None for incomparable columns."""
    if pd.api.types.is_bool_dtype(values) or pd.api.types.is_float_dtype(values) and not (values.dropna() % 1 == 0).all():
        return None
    if pd.api.types.is_float_dtype(values):
        values = values.dropna().astype("int64")
    return set(values.dropna().astype(str).str.strip())


def discover(tables, min_containment=0.9, min_distinct=2, min_name_similarity=0.5) -> pd.DataFrame:
    columns = {(t, str(c)): key_values(frame[c]) for t, (_, frame) in tables.items() for c in frame.columns}
    columns = {k: v for k, v in columns.items() if v}
    keys = {(t, c) for t, (_, frame) in tables.items() for c in frame.columns
            if (t, str(c)) in columns and frame[c].notna().all() and frame[c].is_unique}
    rows = []
    for (ft, fc), values in columns.items():
        if len(values) < min_distinct:
            continue
        for tt, tc in keys:
            if tt == ft:
                continue
            containment = len(values & columns[tt, str(tc)]) / len(values)
            similarity = difflib.SequenceMatcher(None, fc.lower(), str(tc).lower()).ratio()
            # Containment alone mismatches years, small integers etc. to many other tables; column name similarity is the cheapest filter.
            if containment >= min_containment and similarity >= min_name_similarity:
                rows.append({"from_table": ft, "from_column": fc, "to_table": tt, "to_column": str(tc),
                             "containment": containment, "from_distinct": len(values), "name_similarity": similarity})
    frame = pd.DataFrame(rows, columns=["from_table", "from_column", "to_table", "to_column",
                                        "containment", "from_distinct", "name_similarity"])
    return frame.sort_values(["containment", "name_similarity", "from_distinct"], ascending=False, ignore_index=True)


def findings(candidates, tables, min_containment):
    units = []
    for i, r in enumerate(candidates.to_dict("records")):
        src, dst = tables[r["from_table"]][0], tables[r["to_table"]][0]
        units.append({
            "id": f"joins/{i}", "form": "finding", "status": "inferred",
            "content": f"可能的 join：{r['from_table']}.{r['from_column']} → {r['to_table']}.{r['to_column']}"
                       f"（包含率 {r['containment']:.2f}）",
            "condition": "取值包含关系，未验证语义",
            "provenance": f"tool:joins@0.1(min_containment={min_containment}) ; {src}#col/{r['from_column']} ; {dst}#col/{r['to_column']}",
            "meta": r,
        })
    return units


def draft(name, tables, candidates) -> dict:
    keys = {}
    for t, (_, frame) in tables.items():
        unique = [str(c) for c in frame.columns if frame[c].notna().all() and frame[c].is_unique]
        named = [c for c in unique if any(k in c.lower() for k in ("id", "key", "code"))]
        if unique:
            keys[t] = [(named or unique)[0]]
    relationships = [
        ontology.relationship(ontology.snake(r.from_table), [r.from_column], ontology.snake(r.to_table), [r.to_column],
                              confidence=round(r.containment, 3))
        for r in candidates.drop_duplicates(["from_table", "from_column"]).itertuples()
    ]
    return ontology.from_tables(name, {t: frame for t, (_, frame) in tables.items()}, keys, relationships,
                                provenance={"method": "tool", "author": "knosis.tools.joins@0.1"})


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--tables", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-containment", type=float, default=0.9)
    parser.add_argument("--min-distinct", type=int, default=2)
    parser.add_argument("--min-name-similarity", type=float, default=0.5)
    parser.add_argument("--ontology", help="directory for the draft ontology core layer")
    parser.add_argument("--name", default="draft")
    args = parser.parse_args(argv)
    started = time.monotonic()
    tables = read_tables(args.tables)
    candidates = discover(tables, args.min_containment, args.min_distinct, args.min_name_similarity)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(out / "joins.csv", index=False)
    if args.ontology:
        ontology.write_ontology(args.ontology, {"semantic_model": draft(args.name, tables, candidates)})
    write_result(out, "joins", vars(args), findings(candidates, tables, args.min_containment), started)
    print(candidates.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
