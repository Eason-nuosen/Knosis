"""Run SQL over CSV / parquet tables (in-memory SQLite)."""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

import pandas as pd

from knosis.tools import read_tables, write_result


def connect(tables) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    for name, (_, frame) in tables.items():
        frame.to_sql(name, conn, index=False)
    return conn


def statements(sql: str):
    """Split on semicolons, but not inside string literals."""
    buffer = ""
    for part in sql.split(";"):
        buffer += part + ";"
        if sqlite3.complete_statement(buffer):
            if buffer.strip(" ;\n\t"):
                yield buffer
            buffer = ""


def execute(conn, sql: str) -> pd.DataFrame | None:
    result = None
    for statement in statements(sql):
        cursor = conn.execute(statement)
        if cursor.description:
            result = pd.DataFrame(cursor.fetchall(), columns=[d[0] for d in cursor.description])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--tables", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query")
    group.add_argument("--file")
    group.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    started = time.monotonic()
    tables = read_tables(args.tables)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.list:
        result = pd.DataFrame([{"table": name, "file": str(path), "rows": len(frame), "columns": ", ".join(map(str, frame.columns))}
                               for name, (path, frame) in tables.items()])
    else:
        result = execute(connect(tables), args.query or Path(args.file).read_text(encoding="utf-8"))
    if result is not None:
        result.to_csv(out / "result.csv", index=False)
        print(result.head(20).to_string(index=False))
    write_result(out, "sql", vars(args), [], started)


if __name__ == "__main__":
    main()
