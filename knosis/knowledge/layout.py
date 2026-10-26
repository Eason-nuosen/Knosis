"""知识层的目录布局（v0.5）：工作区与独立知识库同布局，分成两大块。

    <root>/
    ├── kb/                         知识主体：永久保存、可继承、可被选取
    │   ├── knowledge/
    │   │   ├── units.jsonl         κ：对象知识（instance / relation / dataset）+ 元知识（method / usage）
    │   │   └── ontology/           结构化知识（OSI 标准的三层：语义模型 / 概念 / 映射）
    │   ├── skills/<名字>/SKILL.md  使用流程
    │   ├── outline.yaml            知识体系大纲（树）
│   ├── graph.json              知识图谱：实体与关系，每条边引用单元
│   └── flows/<名字>.json       流程图：步骤、检查、判断，每个节点引用单元或 skill
    └── evidence/                   来源与验证的全过程
        ├── ledger.jsonl            证据账本
        ├── consolidate.jsonl       内化操作记录（去重、矛盾处理、构建知识体系）
        ├── checks/                 可执行检查
        ├── feedback/               dev 反馈记录
        └── traces/                 来源轨迹（知识库收集来的会话）

`root` 是工作区根、知识库根，或工作区里的一个知识版本快照（`stages/<阶段>/`）。
"""

from __future__ import annotations

from pathlib import Path

UNITS = "kb/knowledge/units.jsonl"
ONTOLOGY = "kb/knowledge/ontology"
SKILLS = "kb/skills"
OUTLINE = "kb/outline.yaml"
LEDGER = "evidence/ledger.jsonl"
ACTIONS = "evidence/consolidate.jsonl"
CHECKS = "evidence/checks"
FEEDBACK = "evidence/feedback"
TRACES = "evidence/traces"
PARTS = ("kb", "evidence")


class Layout:
    def __init__(self, root):
        self.root = Path(root)

    def __getattr__(self, name):
        rel = {"units": UNITS, "ontology": ONTOLOGY, "skills": SKILLS, "outline": OUTLINE, "ledger": LEDGER,
               "actions": ACTIONS, "checks": CHECKS, "feedback": FEEDBACK, "traces": TRACES,
               "kb": "kb", "knowledge": "kb/knowledge", "evidence": "evidence"}.get(name)
        if rel is None:
            raise AttributeError(name)
        return self.root / rel


def layout(root) -> Layout:
    """布局对象；遇到 v0.4 的旧布局（`knowledge/units.jsonl` 或根目录下的 `units.jsonl`）时提示迁移。"""
    root = Path(root)
    if not (root / "kb").is_dir() and ((root / "knowledge/units.jsonl").exists() or (root / "units.jsonl").exists()):
        raise RuntimeError(f"{root} uses the v0.4 layout; run `knosis migrate {root}` first")
    return Layout(root)


def is_workspace(root) -> bool:
    return (Path(root) / ".knosis/state.json").exists()


def data_root(root):
    """检查 `data/` 来源与数据指纹用的根：工作区是自己，知识库与快照没有（返回 None）。"""
    return Path(root).resolve() if is_workspace(root) else None


def ensure(root) -> Layout:
    lay = Layout(root)
    for path in (lay.knowledge, lay.skills, lay.checks, lay.feedback):
        path.mkdir(parents=True, exist_ok=True)
    for path in (lay.units, lay.ledger):
        if not path.exists():
            path.write_text("", encoding="utf-8")
    return lay
