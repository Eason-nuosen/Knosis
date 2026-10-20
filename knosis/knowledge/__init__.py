"""知识层：κ 单元（`units.jsonl`）+ 证据账本（`evidence.jsonl`）+ 本体（Ossie 三文件，本体元素也是 κ）+ 反馈记录。

工作区或知识库里的知识层目录：

    units.jsonl          每行一个 κ
    evidence.jsonl       每行一条证据（支持 / 反驳 / 无法判定 / 不适用），见 `evidence`
    ontology/            可选；<name>.{semantic_model,ontology,mapping}.yaml，或每个本体一个子目录
    checks/              可选；单元的可执行检查脚本
    feedback/            dev 题上的反馈记录，见 `feedback`
"""

from pathlib import Path

from . import feedback
from .evidence import add_evidence, by_unit, check_evidence, load_evidence, trace, verify
from .ontology import check_ontology, load_ontology, ontology_units, refs, write_ontology
from .units import FORMS, INACTIVE, STATUSES, active, check_units, load_units, write_units

__all__ = [
    "FORMS", "STATUSES", "INACTIVE", "load_units", "write_units", "check_units", "active",
    "load_ontology", "write_ontology", "check_ontology", "ontology_units", "refs", "check_knowledge",
    "ontology_docs", "all_ontology_units", "load_evidence", "add_evidence", "check_evidence", "by_unit",
    "verify", "trace",
]


def ontology_docs(directory) -> dict[str, dict]:
    """知识层里的全部本体：`ontology/` 下直接放的三文件记为 ""，每个含三文件的子目录记为子目录名。"""
    root = Path(directory) / "ontology"
    if not root.is_dir():
        return {}
    docs = {"": load_ontology(root)} if any(root.glob("*.yaml")) else {}
    docs |= {sub.name: load_ontology(sub) for sub in sorted(root.iterdir()) if sub.is_dir() and any(sub.glob("*.yaml"))}
    return docs


def all_ontology_units(docs: dict[str, dict]) -> list[dict]:
    units = []
    for name, d in docs.items():
        for unit in ontology_units(d, prefix=str(Path("knowledge/ontology") / name)):
            units.append({**unit, "id": unit["id"].replace("ontology/", f"ontology/{name}/", 1) if name else unit["id"]})
    return units


def check_knowledge(directory, known_ids=frozenset(), root=None) -> list[str]:
    """检查一个知识层目录：κ 结构、状态与证据一致、证据账本、本体跨文件引用、κ 的 `about` 能否解析。

    `root`：工作区目录，给定时检查 `data/` 来源与证据的数据指纹；知识库没有数据，不给。
    """
    directory = Path(directory)
    docs = ontology_docs(directory)
    issues = [issue for d in docs.values() for issue in check_ontology(d)]
    names = set().union(*(refs(d) for d in docs.values())) if docs else None
    units = load_units(directory / "units.jsonl")
    entries = load_evidence(directory)
    issues += check_units(units, known_ids, root, names, evidence=by_unit(entries, root))
    ids = {u["id"] for u in units} | set(known_ids) | {u["id"] for u in all_ontology_units(docs)}
    issues += check_evidence(entries, ids, root)
    return issues
