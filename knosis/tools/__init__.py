"""工具层：每个工具一个目录 `<name>/{TOOL.md, run.py}`，以独立进程运行；核心包不导入神经模型。

新增工具：建目录，写带 YAML 头的 TOOL.md（name / version / kind / modality / stage / license）
和一个命令行 run.py；输出目录里用 `write_result` 写 `units.jsonl` 与 `run.json`。
工具只产出注解，不改数据；注解一律是 inferred 或 observed 的 κ。
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
    """重模型在自己的环境里跑：`KNOSIS_<NAME>_PYTHON` 指定解释器，默认当前解释器。"""
    python = os.environ.get(f"KNOSIS_{name.upper()}_PYTHON", sys.executable)
    return subprocess.run([python, str(TOOLS_DIR / name / "run.py"), *args]).returncode


def tools_markdown(modalities) -> str:
    sections = ["# 可用工具\n\n用 `knosis tool run <name> -- <参数>` 调用。工具只输出注解，不改数据；"
                "输出的 κ 是 inferred / observed，采纳前要在数据上验证。\n"
                "神经模型工具需单独环境，`--prepare-only` 只检查输入，不产生推断。"]
    seen = set()
    for modality in modalities:
        for tool in list_tools(modality):
            if tool["name"] in seen:
                continue
            seen.add(tool["name"])
            body = card(tool["name"]).split("---", 2)[2].strip()
            sections.append(f"## {tool['name']} @{tool['version']}（{tool['kind']}）\n\n许可：{tool['license']}\n\n{body}")
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


# ---------------------------------------------------------------- 表格工具共用


def table_name(path: Path) -> str:
    """SQL 可用的表名（与 BI-Agent 的 sanitize 一致：非字母数字转下划线，数字开头加下划线）。"""
    name = re.sub(r"[^A-Za-z0-9]", "_", path.stem.replace("'", "").replace('"', ""))
    return f"_{name}" if name[:1].isdigit() else name


def read_tables(paths) -> dict[str, tuple[Path, "pd.DataFrame"]]:
    """目录展开为其中的 csv / parquet；返回 {表名: (路径, DataFrame)}。下划线开头的文件是元数据，跳过。"""
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
        else:  # 真实 BI 项目里有空表文件
            frame = pd.read_csv(f, low_memory=False) if f.stat().st_size else pd.DataFrame()
        tables[table_name(f)] = (f, frame)
    return tables
