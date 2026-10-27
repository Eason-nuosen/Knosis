"""Table profiling: column stats + table-level schema κ + suspicious-item findings."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import pandas as pd

from knosis.tools import read_tables, write_result

PERIOD = re.compile(
    r"^((19|20)\d\d([-/_ ]?\d\d?)?|q[1-4]|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?([-/_ ]?\d+)?)$", re.I,
)


def profile_column(table, column, values: pd.Series) -> dict:
    numeric = pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values)
    non_null = values.dropna()
    return {
        "table": table, "column": str(column), "dtype": str(values.dtype), "rows": len(values),
        "missing": float(values.isna().mean()) if len(values) else 0.0,
        "distinct": int(non_null.nunique()),
        "unique": bool(len(non_null) == len(values) and non_null.is_unique and len(values) > 0),
        "min": non_null.min().item() if numeric and len(non_null) else None,
        "max": non_null.max().item() if numeric and len(non_null) else None,
        "examples": " | ".join(map(str, non_null.drop_duplicates().head(5))),
    }


def findings(table, path, rows, max_missing, min_period_columns):
    units = []
    keys = [r["column"] for r in rows if r["unique"]]
    n = rows[0]["rows"] if rows else 0
    units.append({
        "id": f"profile/{table}", "form": "schema", "status": "observed",
        "content": f"表 {table}：{n} 行，{len(rows)} 列；候选主键（非空且唯一）：{keys or '无'}",
        "provenance": f"tool:profile@0.1() ; {path}",
        "meta": {"rows": n, "columns": [r["column"] for r in rows], "key_candidates": keys},
    })
    for r in rows:
        location = f"tool:profile@0.1(max_missing={max_missing}) ; {path}#col/{r['column']}"
        if r["distinct"] <= 1 and n > 1:
            units.append({"id": f"profile/{table}/{r['column']}/constant", "form": "finding", "status": "inferred",
                          "content": f"{table}.{r['column']} 取值恒定（{r['examples'] or '全空'}）",
                          "condition": "只看当前文件", "provenance": location, "meta": r})
        elif r["missing"] > max_missing:
            units.append({"id": f"profile/{table}/{r['column']}/missing", "form": "finding", "status": "inferred",
                          "content": f"{table}.{r['column']} 缺失率 {r['missing']:.1%}",
                          "condition": "只看当前文件", "provenance": location, "meta": r})
    periods = [r["column"] for r in rows if PERIOD.match(r["column"].strip())]
    if len(periods) >= min_period_columns:
        units.append({
            "id": f"profile/{table}/wide", "form": "finding", "status": "inferred",
            "content": f"{table} 疑似宽表：{len(periods)} 列的列名像时间（{', '.join(periods[:6])} …），可能需要 unpivot 成长表",
            "condition": "按列名启发式判断", "provenance": f"tool:profile@0.1() ; {path}",
            "meta": {"period_columns": periods},
        })
    return units


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--tables", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-missing", type=float, default=0.5)
    parser.add_argument("--min-period-columns", type=int, default=4)
    args = parser.parse_args(argv)
    started = time.monotonic()
    rows, units = [], []
    for table, (path, frame) in read_tables(args.tables).items():
        table_rows = [profile_column(table, c, frame[c]) for c in frame.columns]
        rows += table_rows
        units += findings(table, path, table_rows, args.max_missing, args.min_period_columns)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "profile.csv", index=False)
    write_result(out, "profile", vars(args), units, started)
    print(f"{len(rows)} columns, {len(units)} units -> {out}")


if __name__ == "__main__":
    main()
