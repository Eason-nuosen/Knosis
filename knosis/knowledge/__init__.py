"""知识层：κ 单元（`units.jsonl`）+ 本体子层（Ossie 三文件，见 `ontology`）。

工作区里的知识层目录：

    knowledge/units.jsonl          每行一个 κ
    knowledge/ontology/            可选；<name>.{semantic_model,ontology,mapping}.yaml
    knowledge/feedback/            dev 题上的反馈记录，见 `feedback`
"""

from pathlib import Path

from . import feedback
from .ontology import check_ontology, load_ontology, ontology_units, refs, write_ontology
from .units import FORMS, INACTIVE, STATUSES, active, check_units, load_units, write_units

__all__ = [
    "FORMS", "STATUSES", "INACTIVE", "load_units", "write_units", "check_units", "active",
    "load_ontology", "write_ontology", "check_ontology", "ontology_units", "refs", "check_knowledge",
]


def check_knowledge(directory, known_ids=frozenset(), root=None) -> list[str]:
    """检查一个知识层目录：κ 结构、本体跨文件引用、κ 的 `about` 能否解析到本体元素。"""
    directory = Path(directory)
    docs = load_ontology(directory / "ontology") if (directory / "ontology").is_dir() else {}
    issues = check_ontology(docs)
    issues += check_units(load_units(directory / "units.jsonl"), known_ids, root, refs(docs) if docs else None)
    return issues
