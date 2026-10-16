"""知识单元 κ 的 JSONL 存储与结构检查；只守结构，不判断内容对错。"""

from __future__ import annotations

import json
from pathlib import Path

FORMS = {"finding", "fact", "rule", "formula", "schema", "tool"}
STATUSES = {"observed", "inferred", "verified", "retracted", "stale"}
INACTIVE = {"retracted", "stale"}
REQUIRED = ("id", "content", "form", "provenance", "status")


def load_units(path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_units(path, units: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        "".join(json.dumps(unit, ensure_ascii=False) + "\n" for unit in units), encoding="utf-8",
    )


def check_units(units, known_ids=frozenset(), root: Path | None = None, ontology_refs=None) -> list[str]:
    """返回问题清单，空 = 通过。

    `known_ids`：历史版本出现过的 id（I1）；`root`（工作区）：给定时检查 `data/` 来源文件与
    `feedback:` 记录存在；
    `ontology_refs`：给定时检查 `about` 里引用的本体元素存在（见 `ontology.refs`）。
    """
    issues = []
    by_id = {unit["id"]: unit for unit in units if unit.get("id")}
    available = set(by_id) | set(known_ids)
    seen = set()
    for i, unit in enumerate(units):
        name = unit.get("id") or f"line {i + 1}"
        for key in REQUIRED:
            if not unit.get(key):
                issues.append(f"{name}: missing {key}")
        if name in seen:
            issues.append(f"{name}: duplicate id")
        seen.add(name)
        for key, choices in (("form", FORMS), ("status", STATUSES)):
            if unit.get(key) not in choices:
                issues.append(f"{name}: invalid {key}: {unit.get(key)}")
        parents = unit.get("derived_from", [])
        sources = [s.strip() for s in unit.get("provenance", "").split(";")]
        if "derived" in sources and not parents:
            issues.append(f"{name}: derived provenance requires derived_from")
        for source in sources:
            if root is not None and source.startswith("data/"):
                path = (Path(root) / source.split("#", 1)[0]).resolve()
                if not path.is_relative_to(Path(root).resolve() / "data") or not path.exists():
                    issues.append(f"{name}: missing data source: {source}")
            if root is not None and source.startswith("feedback:"):
                record = source.split("#", 1)[0].removeprefix("feedback:")
                if not (Path(root) / "knowledge/feedback" / f"{record}.json").exists():
                    issues.append(f"{name}: missing feedback record: {source}")
        for parent in parents:
            if parent not in available:
                issues.append(f"{name}: unknown derived_from: {parent}")
            # I5：父单元失效，后代必须跟着失效。
            if by_id.get(parent, {}).get("status") in INACTIVE and unit.get("status") not in INACTIVE:
                issues.append(f"{name}: inactive parent {parent} requires stale or retracted status")
        if ontology_refs is not None:
            for ref in unit.get("about", []):
                if ref not in ontology_refs:
                    issues.append(f"{name}: unknown ontology ref in about: {ref}")
    return issues


def active(units) -> list[dict]:
    """decide 阶段可用的单元。"""
    return [unit for unit in units if unit.get("status") not in INACTIVE]
