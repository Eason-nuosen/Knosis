"""Tool layer: one directory per tool, `<name>/{TOOL.md, run.py}`, run as a separate process; the core package never imports neural models.

To add a tool: create the directory, write a TOOL.md with a YAML header (name / version / kind / modality / stage / license)
and a command-line run.py; in the output directory, use `write_result` to write `units.jsonl` and `run.json`.
Tools only produce annotations and never modify data; annotations are always inferred or observed κ.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

TOOLS_DIR = Path(__file__).parent


def list_tools(modality=None) -> list[dict]:
    tools = []
    for path in sorted(TOOLS_DIR.glob("*/TOOL.md")):
        info = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
        if modality is None or modality in info["modality"]:
            tools.append(info)
    return tools


def card(name) -> str:
    return (TOOLS_DIR / name / "TOOL.md").read_text(encoding="utf-8")


def run_tool(name, args: list[str]) -> int:
    """Heavy models run in their own environment: `KNOSIS_<NAME>_PYTHON` sets the interpreter, defaulting to the current one."""
    python = os.environ.get(f"KNOSIS_{name.upper()}_PYTHON", sys.executable)
    return subprocess.run([python, str(TOOLS_DIR / name / "run.py"), *args]).returncode


def available(info) -> bool:
    """Whether a model tool's dependencies (`requires` in `TOOL.md`) import in its interpreter."""
    python = os.environ.get(f"KNOSIS_{info['name'].upper()}_PYTHON", sys.executable)
    code = "; ".join(f"import {module}" for module in info.get("requires", []))
    return not code or subprocess.run([python, "-c", code], capture_output=True).returncode == 0


def tools_markdown(modalities) -> str:
    sections = ["# 可用工具\n\n用 `knosis tool run <name> -- <参数>` 调用。工具只输出注解，不改数据；"
                "输出的 κ 是 inferred / observed，采纳前要在数据上验证。\n"
                "模型类工具标明了在本机能否做真实推断；不能时 `--prepare-only` 只检查输入，不产生推断。"]
    seen = set()
    for modality in modalities:
        for tool in list_tools(modality):
            if tool["name"] in seen:
                continue
            seen.add(tool["name"])
            body = card(tool["name"]).split("---", 2)[2].strip()
            state = ""
            if tool["kind"] == "model":
                state = ("本机状态：依赖已安装，可以直接做真实推断。\n\n" if available(tool)
                         else f"本机状态：缺少依赖（{', '.join(tool.get('requires', []))}），只能 `--prepare-only`。\n\n")
            sections.append(f"## {tool['name']} @{tool['version']}（{tool['kind']}）\n\n许可：{tool['license']}\n\n{state}{body}")
    return "\n\n".join(sections) + "\n"


def write_result(out, name, params, units, started):
    from ..knowledge import write_units

    info = yaml.safe_load(card(name).split("---", 2)[1])
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_units(out / "units.jsonl", units)
    record = {"tool": name, "version": info["version"], "parameters": params,
              "seconds": time.monotonic() - started}
    (out / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- shared by table tools


def table_name(path: Path) -> str:
    """SQL-safe table name (same as BI-Agent's sanitize: non-alphanumerics become underscores, a leading digit gets an underscore prefix)."""
    name = re.sub(r"[^A-Za-z0-9]", "_", path.stem.replace("'", "").replace('"', ""))
    return f"_{name}" if name[:1].isdigit() else name


def read_tables(paths) -> dict[str, tuple[Path, "pd.DataFrame"]]:
    """Directories expand to their csv / parquet files; returns {table name: (path, DataFrame)}. Files starting with an underscore are metadata and skipped."""
    import pandas as pd

    files = []
    for p in map(Path, paths):
        files += sorted(f for f in p.iterdir() if f.suffix in (".csv", ".parquet")) if p.is_dir() else [p]
    tables = {}
    for f in files:
        if f.name.startswith("_"):
            continue
        if f.suffix == ".parquet":
            frame = pd.read_parquet(f)
        else:  # real BI projects contain empty table files
            frame = pd.read_csv(f, low_memory=False) if f.stat().st_size else pd.DataFrame()
        tables[table_name(f)] = (f, frame)
    return tables
