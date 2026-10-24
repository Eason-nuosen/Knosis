"""证据账本：`evidence/ledger.jsonl`，每行一次验证结果。

    {"id": "e-007", "unit": "<κ id>", "verdict": "support", "method": "check",
     "source": "tool:tabpfn@0.2(cv,...)", "note": "...", "inputs": {"data/train.parquet": "<指纹>"}, "created": "..."}

`verdict`：support（支持）/ refute（反驳）/ undetermined（无法判定：条件或测量无法确认）/
not_applicable（前提不成立，不算支持也不算反例）。
`method`：check（Knosis 重跑单元的可执行检查）/ tool / data / feedback / ablation（去掉该知识对比）/ derivation / human。
`inputs`：这条证据依赖的数据文件指纹；文件变了，证据就过期，相关知识需要重验或标为 stale。
知识的状态仍由 agent 写，`units.check_units` 检查它和证据是否一致。
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .layout import layout
from .units import load_units, source_issues, write_units

VERDICTS = {"support", "refute", "undetermined", "not_applicable"}
METHODS = {"check", "tool", "data", "feedback", "ablation", "derivation", "human"}


def load_evidence(root) -> list[dict]:
    """`root`：工作区、知识库或知识版本快照。"""
    path = layout(root).ledger
    return load_units(path) if path.exists() else []


def add_evidence(root, entries) -> list[dict]:
    """追加证据，补上 id 与 created。"""
    old = load_evidence(root)
    now = datetime.now(timezone.utc).isoformat()
    new = [{"id": f"e-{len(old) + i + 1:04d}", **entry, "created": entry.get("created", now)}
           for i, entry in enumerate(entries)]
    write_units(layout(root).ledger, old + new)
    return new


def fingerprint(path) -> str:
    stat = Path(path).stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def data_inputs(root, paths=None) -> dict:
    """`paths`（相对工作区）的指纹；不给就取 `data/` 下所有文件。"""
    root = Path(root)
    files = [root / p for p in paths] if paths else sorted(p for p in (root / "data").rglob("*") if p.is_file())
    return {str(p.relative_to(root)): fingerprint(p) for p in files}


def expired(entry, root) -> list[str]:
    """证据依赖的数据文件里已变化或消失的。继承来的证据：文件不存在说明换了环境布局，不在这里判定；存在而内容变了才算过期。"""
    root = Path(root)
    gone = lambda p: not (root / p).exists()  # noqa: E731
    return [p for p, fp in entry.get("inputs", {}).items()
            if (not entry.get("inherited") and gone(p)) or (not gone(p) and fingerprint(root / p) != fp)]


def check_evidence(entries, unit_ids, root=None) -> list[str]:
    issues = []
    for entry in entries:
        name = entry.get("id", "?")
        for key in ("id", "unit", "verdict", "method", "source"):
            if not entry.get(key):
                issues.append(f"evidence {name}: missing {key}")
        if entry.get("verdict") not in VERDICTS:
            issues.append(f"evidence {name}: invalid verdict: {entry.get('verdict')}")
        if entry.get("method") not in METHODS:
            issues.append(f"evidence {name}: invalid method: {entry.get('method')}")
        if entry.get("unit") not in unit_ids:
            issues.append(f"evidence {name}: unknown unit: {entry.get('unit')}")
        for source in str(entry.get("source", "")).split(";"):
            issues += [f"evidence {name}: {issue}" for issue in source_issues(source.strip(), root, bool(entry.get("inherited")))]
    return issues


def by_unit(entries, root=None) -> dict[str, list[dict]]:
    """每个单元的有效证据（未过期），按记录顺序。"""
    grouped = {}
    for entry in entries:
        if root is None or not expired(entry, root):
            grouped.setdefault(entry["unit"], []).append(entry)
    return grouped


# ---------------------------------------------------------------- 可执行检查


def run_check(unit, root, tables=None) -> tuple[str, str]:
    """跑单元的 `check`，返回 (verdict, note)。

    sql：`{"kind": "sql", "query": ..., "expect": [[...]]}`，在 `data/` 的表上（或给定 `tables`）执行；
    有 expect 时结果行相等即支持，否则第一行全部为真即支持。
    python：`{"kind": "python", "path": "evidence/checks/<id>.py"}`，在工作区根目录运行；
    退出码 0 支持，1 反驳，其他无法判定；stdout 末尾几行作为 note。
    """
    check, root = unit["check"], Path(root)
    if check["kind"] == "sql":
        from ..tools import read_tables
        from ..tools.sql.run import connect, execute

        tables = tables if tables is not None else {name: frame for name, (_, frame) in read_tables([root / "data"]).items()}
        frame = execute(connect({name: (None, f) for name, f in tables.items()}), check["query"])
        rows = [] if frame is None else frame.values.tolist()
        if "expect" in check:
            ok = len(rows) == len(check["expect"]) and all(
                len(a) == len(b) and all(same(x, y) for x, y in zip(a, b)) for a, b in zip(rows, check["expect"]))
        else:
            ok = bool(rows) and all(bool(x) for x in rows[0])
        return ("support" if ok else "refute"), f"rows={json.dumps(rows[:5], default=str)}"
    result = subprocess.run([sys.executable, check["path"]], cwd=root, capture_output=True, text=True)
    verdict = {0: "support", 1: "refute"}.get(result.returncode, "undetermined")
    return verdict, "\n".join((result.stdout + result.stderr).strip().splitlines()[-5:])


def same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))
    return a == b


def verify(ws, ids=None) -> list[dict]:
    """重跑带 `check` 的活跃单元（或指定的 `ids`），把结果追加为 method=check 的证据。"""
    ws = Path(ws)
    units = [u for u in load_units(layout(ws).units)
             if "check" in u and (u["id"] in ids if ids else u["status"] not in {"retracted", "stale", "merged"})]
    entries = []
    for unit in units:
        verdict, note = run_check(unit, ws)
        check = unit["check"]
        inputs = data_inputs(ws, check.get("inputs"))
        if check["kind"] == "python":
            inputs[check["path"]] = fingerprint(ws / check["path"])
        entries.append({"unit": unit["id"], "verdict": verdict, "method": "check",
                        "source": f"check:{unit['id']}", "note": note, "inputs": inputs})
    return add_evidence(ws, entries)


def trace(root, unit_id, history=()) -> str:
    """一条知识的发现途径：派生链 + 每条证据，按时间排列，markdown。`history` 是历史快照里的单元。"""
    units = {u["id"]: u for u in [*history, *load_units(layout(root).units)]}
    evidence = by_unit(load_evidence(root))
    lines, seen = [], set()

    def walk(uid, depth):
        if uid in seen:
            return
        seen.add(uid)
        unit = units.get(uid, {"content": "（未知单元）", "status": "?", "form": "?"})
        pad = "  " * depth
        lines.append(f"{pad}- **{uid}** [{unit['form']}/{unit['status']}] {unit['content']}")
        if unit.get("condition"):
            lines.append(f"{pad}  - 条件：{unit['condition']}")
        lines.append(f"{pad}  - 来源：{unit.get('provenance', '')}")
        for key, label in (("merged_into", "已并入"), ("superseded_by", "被替换为"), ("conflicts_with", "与之矛盾")):
            if unit.get(key):
                lines.append(f"{pad}  - {label}：{unit[key]}")
        for entry in evidence.get(uid, []):
            note = entry.get("note", "")
            note = note if len(note) <= 300 else note[:300] + " …"
            lines.append(f"{pad}  - {entry['created'][:19]} {entry['verdict']}（{entry['method']}，{entry['source']}）{note}")
        for parent in unit.get("derived_from", []):
            walk(parent, depth + 1)

    walk(unit_id, 0)
    return "\n".join(lines) + "\n"
