"""知识单元 κ 的 JSONL 存储与结构检查；只守结构与「状态—证据」一致性，不判断内容对错。"""

from __future__ import annotations

import json
from pathlib import Path

from .layout import FEEDBACK

# procedure：步骤型表达（如「如何验证某类知识」的步骤），可附可执行检查。
FORMS = {"finding", "fact", "rule", "formula", "schema", "tool", "procedure"}
# contested：有反驳证据、尚未定论；默认不被选取，使用者应知道它有争议。
# merged：去重时并入另一条（`merged_into`），只作为别名保留；stale：环境变化后失效，可由 `superseded_by` 指向新版本。
STATUSES = {"observed", "inferred", "verified", "contested", "retracted", "stale", "merged"}
INACTIVE = {"retracted", "stale", "merged"}
# 粒度。对象知识（关于环境）：instance 某个具体对象；relation 对象之间的结构（join、本体关系）；
# dataset 这份数据整体的规律 / 分布 / 公式。元知识（关于知识）：method 怎么得到知识（发现与验证的方法）；
# usage 怎么用好知识（哪些知识 / skill 在什么任务、什么读者下有效，由反馈或消融支持）。
# 与 form（表达形式）正交；不写时由 `scope_of` 推断。
SCOPES = ("instance", "relation", "dataset", "method", "usage")
META = {"method", "usage"}
POINT = ("#node/", "#edge/", "#row/")
REQUIRED = ("id", "content", "form", "provenance", "status")


def load_units(path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_units(path, units: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        "".join(json.dumps(unit, ensure_ascii=False) + "\n" for unit in units), encoding="utf-8",
    )


def source_issues(source: str, root=None, inherited=False) -> list[str]:
    """一个来源能否定位：`data/` 文件存在且在工作区数据目录内，`kb/` / `evidence/` 文件（如继承来的轨迹）存在，`feedback:` 记录存在。

    `inherited`：从知识库继承来的单元 / 证据，`data/` 指的是产生它时的环境，新工作区的数据布局可能不同，不检查。
    """
    if root is None or inherited and source.startswith("data/"):
        return []
    root = Path(root)
    if source.startswith("data/"):
        path = (root / source.split("#", 1)[0]).resolve()
        if not path.is_relative_to(root.resolve() / "data") or not path.exists():
            return [f"missing data source: {source}"]
    if source.startswith(("kb/", "evidence/")) and not (root / source.split("#", 1)[0]).exists():
        return [f"missing source: {source}"]
    if source.startswith("feedback:"):
        record = source.split("#", 1)[0].removeprefix("feedback:")
        if not (root / FEEDBACK / f"{record}.json").exists():
            return [f"missing feedback record: {source}"]
    return []


def scope_of(unit) -> str:
    """显式的 `scope`；否则 procedure 形式 → method，join / 关系类 schema → relation，
    来源全部定位到单个节点 / 边 / 行 → instance，其余 → dataset。"""
    if unit.get("scope"):
        return unit["scope"]
    if unit.get("form") == "procedure":
        return "method"
    text = f"{unit.get('id', '')} {unit.get('provenance', '')}"
    if unit.get("form") == "schema" and any(k in text for k in ("join/", "relation/", "relationship/")):
        return "relation"
    sources = [s.strip() for s in unit.get("provenance", "").split(";") if s.strip()]
    if sources and all(any(p in s for p in POINT) for s in sources):
        return "instance"
    return "dataset"


def level(unit) -> str:
    """object（关于环境）或 meta（关于知识）。"""
    return "meta" if scope_of(unit) in META else "object"


def resolve(uid, by_id, limit=20):
    """沿 `merged_into` 找到别名最终指向的单元 id。"""
    for _ in range(limit):
        target = by_id.get(uid, {}).get("merged_into")
        if not target:
            return uid
        uid = target
    return uid


def check_units(units, known_ids=frozenset(), root: Path | None = None, ontology_refs=None,
                evidence=None) -> list[str]:
    """返回问题清单，空 = 通过。

    `known_ids`：历史版本出现过的 id（I1）；`root`（工作区）：给定时检查 `data/` 来源文件与
    `feedback:` 记录存在；
    `ontology_refs`：给定时检查 `about` 里引用的本体元素存在（见 `ontology.refs`）。
    `evidence`：给定时（`evidence.by_unit` 的结果，只含未过期证据）检查状态与证据一致：
    verified 至少有一条支持；最近一条证据是反驳时须为 contested / retracted / stale；
    I2：`support` 不超过支持证据的独立来源数（来源按 `#` 之前的部分去重）。
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
        if "scope" in unit and unit["scope"] not in SCOPES:
            issues.append(f"{name}: invalid scope: {unit['scope']}")
        parents = unit.get("derived_from", [])
        sources = [s.strip() for s in unit.get("provenance", "").split(";")]
        if "derived" in sources and not parents:
            issues.append(f"{name}: derived provenance requires derived_from")
        inherited = "inherited" in unit.get("meta", {})
        for source in sources:
            issues += [f"{name}: {issue}" for issue in source_issues(source, root, inherited)]
        for parent in parents:
            if parent not in available:
                issues.append(f"{name}: unknown derived_from: {parent}")
            # I5：父单元失效，后代必须跟着失效；并入别的单元（merged）的父单元按合并后的那条算。
            target = by_id.get(resolve(parent, by_id), {})
            if target.get("status") in INACTIVE and unit.get("status") not in INACTIVE:
                issues.append(f"{name}: inactive parent {parent} requires stale or retracted status")
        issues += [f"{name}: {issue}" for issue in consolidation_issues(unit, by_id, available)]
        if evidence is not None:
            issues += [f"{name}: {issue}" for issue in evidence_issues(unit, evidence.get(name, []))]
        if ontology_refs is not None:
            for ref in unit.get("about", []):
                if not ref.startswith("data/") and ref not in ontology_refs:
                    issues.append(f"{name}: unknown ontology ref in about: {ref}")
        # about 也可以直接锚定到数据位置（用于「以对象为键」的反查）。
        for ref in unit.get("about", []):
            if ref.startswith("data/"):
                issues += [f"{name}: about {issue}" for issue in source_issues(ref, root, inherited)]
    return issues


def consolidation_issues(unit, by_id, available) -> list[str]:
    """内化留下的字段：merged_into（去重别名）、superseded_by（版本替换）、conflicts_with（已识别的矛盾）。"""
    issues, status = [], unit.get("status")
    if status == "merged" and not unit.get("merged_into"):
        issues.append("merged requires merged_into")
    if unit.get("merged_into"):
        target = unit["merged_into"]
        if status != "merged":
            issues.append("merged_into requires status merged")
        if target not in by_id:
            issues.append(f"unknown merged_into: {target}")
        elif by_id[resolve(target, by_id)].get("status") in INACTIVE:
            issues.append(f"merged_into {target} must resolve to an active unit")
    if unit.get("superseded_by"):
        if unit["superseded_by"] not in available:
            issues.append(f"unknown superseded_by: {unit['superseded_by']}")
        if status not in {"stale", "retracted"}:
            issues.append("superseded_by requires status stale or retracted")
    for other in unit.get("conflicts_with", []):
        if other not in by_id:
            issues.append(f"unknown conflicts_with: {other}")
        elif status not in INACTIVE and by_id[other].get("status") not in INACTIVE and \
                "contested" not in {status, by_id[other].get("status")}:
            issues.append(f"unresolved conflict with {other}: narrow the conditions and drop conflicts_with, "
                          "retract or supersede one side, or mark it contested")
    return issues


def evidence_issues(unit, entries) -> list[str]:
    supports = [e for e in entries if e["verdict"] == "support"]
    issues = []
    if unit.get("status") == "verified" and not supports:
        issues.append("verified requires at least one unexpired support evidence (knosis knowledge evidence add / verify)")
    decisive = [e for e in entries if e["verdict"] in {"support", "refute"}]
    if decisive and decisive[-1]["verdict"] == "refute" and unit.get("status") not in {"contested", *INACTIVE}:
        issues.append(f"latest evidence {decisive[-1]['id']} refutes it; status must be contested, retracted or stale")
    if scope_of(unit) == "usage" and unit.get("status") == "verified" and not any(
            e["method"] in {"feedback", "ablation"} for e in supports):
        issues.append("usage knowledge can only be verified by feedback or ablation evidence")
    roots = {e["source"].split("#", 1)[0] for e in supports}
    if isinstance(unit.get("support"), int) and unit["support"] > len(roots):
        issues.append(f"I2: support={unit['support']} exceeds {len(roots)} independent supporting sources")
    return issues


def active(units) -> list[dict]:
    """decide 阶段可用的单元（含 contested；选取时默认不给它，见 `select`）。"""
    return [unit for unit in units if unit.get("status") not in INACTIVE]
